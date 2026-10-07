#!/usr/bin/env python3
"""
manager_config.py - safe SSH-based editor for the Wazuh manager's ossec.conf.

Unlike wazuh_client.py (HTTP calls to the Server/Indexer/Dashboard APIs), this
talks to the manager host directly over SSH, because integrations, active
response, and log-source modules (office365, ms-graph, aws-s3, custom wodles)
are all configured in /var/ossec/etc/ossec.conf on disk - there is no API for
most of this on-prem.

IMPORTANT: this shells out to the local `ssh`/`scp` binaries. It only works if
the manager host is reachable from wherever this script runs and an SSH key is
authorized. In a sandboxed/agent environment with no route to the on-prem
network, these calls will simply fail to connect - that's expected; run the
script from a host that has network access to the manager (or copy it there).

Every write follows the same flow: backup -> candidate -> xmllint -> apply
-> wazuh-analysisd config test -> restart (only if asked) -> auto-rollback
on any failure. Nothing restarts the manager unless --restart is passed
explicitly.

Env vars:
  WAZUH_SSH_HOST       manager hostname/IP
  WAZUH_SSH_USER       SSH user (needs sudo rights to edit /var/ossec/etc and restart the service)
  WAZUH_SSH_KEY_PATH   path to private key (recommended over password)
  WAZUH_SSH_PORT       default 22
  WAZUH_CONF_PATH      default /var/ossec/etc/ossec.conf

Usage:
  python manager_config.py fetch --out current.xml
  python manager_config.py diff --block new_block.xml
  python manager_config.py apply --block new_block.xml               # validates, does NOT restart
  python manager_config.py apply --block new_block.xml --restart      # validates AND restarts
  python manager_config.py rollback --backup /var/ossec/etc/ossec.conf.bak.20260727-120000
  python manager_config.py list-backups
"""
import argparse
import difflib
import os
import posixpath
import tempfile
import uuid
import subprocess
import sys
import time

def _local_scratch_path(kind):
    """A per-run scratch path on the LOCAL machine (the one running this
    script) - safe to build from tempfile.gettempdir(), because this path is
    only ever opened by local open()/read()/write() calls, never sent to the
    manager.

    These were hardcoded as /tmp/_wazuh_<kind>_ossec.conf. Two apply or diff
    runs at once - two operators, or one operator running a second config
    before the first cleaned up - would clobber each other's candidate file
    mid-flight, and the second run would install the first run's config. A
    fixed /tmp path also does not exist on native Windows.
    """
    return os.path.join(
        tempfile.gettempdir(),
        f"_wazuh_{kind}_{os.getpid()}_{uuid.uuid4().hex[:8]}_ossec.conf",
    ).replace("\\", "/")


def _remote_scratch_path(kind):
    """A per-run scratch path on the REMOTE (manager) host.

    Must NEVER be built from tempfile.gettempdir() - that reports the LOCAL
    machine's temp directory, and when this script runs from a Windows
    workstation that is something like
    "C:/Users/<you>/AppData/Local/Temp/...". scp'd to the manager and passed
    to `xmllint`/`sudo cp` there, that path is not valid: the manager is
    always a Linux host (systemctl, sudo cp, wazuh-analysisd and
    /var/ossec/... appear throughout this script), so its scratch path must
    always be POSIX, regardless of what OS is running this script. Built
    with posixpath, not os.path, for the same reason - os.path.join would
    still follow the LOCAL platform's rules.
    """
    return posixpath.join(
        "/tmp", f"_wazuh_{kind}_{os.getpid()}_{uuid.uuid4().hex[:8]}_ossec.conf"
    )


def _create_local_scratch_file(path):
    """Create an empty scratch file at `path`, mode 0600, before anything
    writes to it.

    Two reasons this has to happen BEFORE any write, not as a chmod after:
    - Our own `open(path, "w")` writes are masked by the process umask
      (typically 022 -> 0644), so the merged candidate - a full ossec.conf,
      integration API keys included - sat world-readable in the shared
      local /tmp for the life of the run.
    - `tmp_current` is filled by the external `scp` binary, not by this
      script's own open() calls, so this script cannot chmod it after scp
      writes without a race; scp itself preserves the mode of an already
      -existing destination file rather than reapplying the umask, so
      creating it 0600 first is what keeps it 0600 once scp writes into it.

    O_EXCL refuses to reuse an existing path outright - the per-run uuid in
    the scratch path already means two runs must never share one file, and
    this makes that a hard guarantee rather than an assumption.
    """
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)


DEFAULT_CONF_PATH = "/var/ossec/etc/ossec.conf"


def cfg():
    host = os.environ.get("WAZUH_SSH_HOST")
    user = os.environ.get("WAZUH_SSH_USER")
    key = os.environ.get("WAZUH_SSH_KEY_PATH")
    port = os.environ.get("WAZUH_SSH_PORT", "22")
    conf_path = os.environ.get("WAZUH_CONF_PATH", DEFAULT_CONF_PATH)
    if not (host and user):
        sys.exit(
            "ERROR: set WAZUH_SSH_HOST and WAZUH_SSH_USER (and ideally "
            "WAZUH_SSH_KEY_PATH) to reach the manager over SSH."
        )
    return host, user, key, port, conf_path


def _ssh_base(host, user, key, port, connect_timeout=None):
    cmd = ["ssh", "-p", port, "-o", "StrictHostKeyChecking=accept-new"]
    if connect_timeout is not None:
        cmd += ["-o", f"ConnectTimeout={connect_timeout}"]
    if key:
        cmd += ["-i", key]
    cmd.append(f"{user}@{host}")
    return cmd


def _scp_base(key, port):
    cmd = ["scp", "-P", port, "-o", "StrictHostKeyChecking=accept-new"]
    if key:
        cmd += ["-i", key]
    return cmd


class SSHTimeout(RuntimeError):
    """An SSH/scp call exceeded its timeout.

    Deliberately a DIFFERENT type from the plain RuntimeError run_remote
    raises for a completed-but-failing command: a timeout means the
    remote-side OUTCOME is genuinely unknown (the command may have finished
    right after the deadline, or mid-write, or never started) - it is not
    simply "unsuccessful". Callers that need to say something honest about
    that unknown (cleanup's own warning, below) catch this specifically
    rather than folding it into the ordinary failure message.
    """


def run_remote(host, user, key, port, remote_cmd, check=True, timeout=None):
    """Run a command on the manager over SSH. remote_cmd is a shell string
    (built carefully by callers - no untrusted interpolation).

    `timeout`, when given, bounds the call TWO ways: `ssh -o
    ConnectTimeout=<timeout>` (so a manager that never answers the TCP
    handshake doesn't hang) and subprocess.run's own `timeout=` (so a
    manager that accepts the connection but then never responds - or a
    wedged local ssh process - doesn't hang either; ConnectTimeout alone
    would not catch that). A timeout raises SSHTimeout (a RuntimeError
    subclass, so existing `except RuntimeError` callers still catch it)."""
    full = _ssh_base(host, user, key, port, connect_timeout=timeout) + [remote_cmd]
    try:
        result = subprocess.run(full, capture_output=True, text=True, check=False,
                                 timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise SSHTimeout(
            f"SSH command timed out after {timeout}s: {remote_cmd}\n"
            f"stdout: {e.stdout}\nstderr: {e.stderr}"
        ) from e
    if check and result.returncode != 0:
        raise RuntimeError(
            f"SSH command failed ({result.returncode}): {remote_cmd}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


def scp_down(host, user, key, port, remote_path, local_path):
    full = _scp_base(key, port) + [f"{user}@{host}:{remote_path}", local_path]
    result = subprocess.run(full, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"scp download failed: {result.stderr}")


def scp_up(host, user, key, port, local_path, remote_path):
    full = _scp_base(key, port) + [local_path, f"{user}@{host}:{remote_path}"]
    result = subprocess.run(full, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"scp upload failed: {result.stderr}")


def insert_block(current_xml, block_xml, anchor=None):
    """Insert `block_xml` into `current_xml`.

    Default: insert just before the closing </ossec_config> tag (the safe,
    generic anchor - every valid ossec.conf has exactly one). If `anchor` is
    given (a tag name, e.g. "integration"), insert after the LAST occurrence
    of that tag's closing tag instead, so related blocks stay grouped.
    """
    block_xml = block_xml.strip()
    if anchor:
        needle = f"</{anchor}>"
        idx = current_xml.rfind(needle)
        if idx == -1:
            raise ValueError(
                f"Anchor </{anchor}> not found in current config; "
                "falling back to end-of-file insertion is safer - omit --anchor."
            )
        insert_at = idx + len(needle)
        return current_xml[:insert_at] + "\n\n  " + block_xml + current_xml[insert_at:]
    needle = "</ossec_config>"
    idx = current_xml.rfind(needle)
    if idx == -1:
        raise ValueError("No </ossec_config> closing tag found - is this a valid ossec.conf?")
    return current_xml[:idx] + "\n  " + block_xml + "\n" + current_xml[idx:]


def cmd_fetch(args):
    host, user, key, port, conf_path = cfg()
    scp_down(host, user, key, port, conf_path, args.out)
    print(f"Fetched {conf_path} -> {args.out}")


def cmd_diff(args):
    host, user, key, port, conf_path = cfg()
    tmp_current = _local_scratch_path("current")
    _create_local_scratch_file(tmp_current)
    try:
        scp_down(host, user, key, port, conf_path, tmp_current)
        with open(tmp_current, encoding="utf-8") as f:
            current = f.read()
        with open(args.block, encoding="utf-8") as f:
            block = f.read()
        candidate = insert_block(current, block, anchor=args.anchor)
        diff = difflib.unified_diff(
            current.splitlines(keepends=True),
            candidate.splitlines(keepends=True),
            fromfile="current ossec.conf",
            tofile="candidate ossec.conf",
        )
        sys.stdout.writelines(diff)
    finally:
        # tmp_current is a full copy of the live ossec.conf, secrets and
        # all - `diff` never installs anything, but it must not leave that
        # copy behind in shared local /tmp any more than `apply` does.
        try:
            os.unlink(tmp_current)
        except OSError:
            pass


def cmd_apply(args):
    host, user, key, port, conf_path = cfg()

    # Every LOCAL resource is prepared BEFORE anything touches the manager:
    # --block is read and validated, and BOTH local scratch files are
    # reserved (0600, empty, via _create_local_scratch_file's O_EXCL) up
    # front - before the remote backup even runs. An O_EXCL collision
    # (astronomically unlikely given the per-run uuid, but not impossible
    # under PID reuse) then fails here, with nothing remote yet touched and
    # no backup yet to explain. `created_locals` records only the paths
    # THIS run actually created - cleanup below iterates that list, not
    # (tmp_current, tmp_candidate) directly, so it can never delete a file
    # that collided with (and therefore belongs to) something else.
    with open(args.block, encoding="utf-8") as f:
        block = f.read()

    tmp_current = _local_scratch_path("current")
    tmp_candidate = _local_scratch_path("candidate")
    created_locals = []
    remote_candidate = None
    backup_path = None

    def _cleanup_scratch():
        # Best-effort on every exit path from the block below - local temp
        # files THIS RUN created, and the remote candidate (a full
        # ossec.conf, integration API keys and all) that step 4/6 left on
        # the manager whether or not the apply went on to succeed. Must
        # never itself raise over whatever exception or exit is already in
        # flight, and must never itself hang or go quiet: a failed remote
        # cleanup means a secret-bearing file is still sitting on the
        # manager, and the operator has to be told that, by name, not left
        # to wonder why `list-backups` or a later `apply` behaves oddly.
        for p in created_locals:
            try:
                os.unlink(p)
            except OSError:
                pass
        if remote_candidate:
            try:
                # 10s: bounds BOTH the TCP handshake (ConnectTimeout) and a
                # manager that accepts the connection but never answers
                # (subprocess timeout) - a hung ssh here must not delay
                # whatever abort message already printed above.
                result = run_remote(host, user, key, port,
                                     f"rm -f {remote_candidate}",
                                     check=False, timeout=10)
                if result.returncode != 0:
                    print(
                        f"WARNING: could not remove the candidate scratch file "
                        f"left on the manager at {remote_candidate} (it holds "
                        f"a full ossec.conf, including any integration API "
                        f"keys) - remove it by hand.\n{result.stderr}",
                        file=sys.stderr,
                    )
            except KeyboardInterrupt:
                # A SECOND Ctrl-C, landing during cleanup itself. Do not let
                # it escape uncaught: a `finally` block that raises REPLACES
                # whatever exception was already propagating (the one whose
                # "nothing was installed" message already printed above),
                # so an unhandled interrupt here would mask that with a bare
                # KeyboardInterrupt carrying no explanation at all.
                print(
                    f"WARNING: cleanup was interrupted before confirming "
                    f"removal of {remote_candidate} on the manager - it may "
                    "still be there; check and remove it by hand.",
                    file=sys.stderr,
                )
            except SSHTimeout:
                # A timeout means the outcome is genuinely UNKNOWN - the
                # remote `rm -f` may have completed right after the
                # deadline. "could not remove" would claim a certainty this
                # does not have.
                print(
                    f"WARNING: removal not confirmed (timed out) for the "
                    f"candidate scratch file at {remote_candidate} on the "
                    "manager - it may or may not still be there; check and "
                    "remove it by hand.",
                    file=sys.stderr,
                )
            except (RuntimeError, OSError) as e:
                # RuntimeError: run_remote's own failure reporting (a
                # completed command that failed - a KNOWN outcome, unlike
                # SSHTimeout above). OSError: subprocess.run can raise this
                # directly (not via run_remote's own check) if the local
                # `ssh` binary itself is missing or unusable mid-run.
                print(
                    f"WARNING: could not remove the candidate scratch file "
                    f"left on the manager at {remote_candidate}: {e}",
                    file=sys.stderr,
                )

    try:
        _create_local_scratch_file(tmp_current)
        created_locals.append(tmp_current)
        _create_local_scratch_file(tmp_candidate)
        created_locals.append(tmp_candidate)

        ts = time.strftime("%Y%m%d-%H%M%S")
        backup_path = f"{conf_path}.bak.{ts}"

        print(f"1/6 Backing up remote {conf_path} -> {backup_path}", file=sys.stderr)
        run_remote(host, user, key, port, f"sudo cp {conf_path} {backup_path}")

        def _nothing_installed(reason):
            return (
                f"{reason} Nothing was installed; the live config at {conf_path} "
                f"was NOT touched. The pre-apply backup taken in step 1/6 remains "
                f"at {backup_path} on the manager (harmless - safe to leave, or "
                "remove it yourself)."
            )

        # This inner try/except is scoped to steps 2/6-4/6 ONLY - everything
        # that can fail before the live config has been touched. Do not
        # widen it to cover the install below: a failure AFTER the
        # `sudo cp {remote_candidate} {conf_path}` in step 5/6 means the
        # live config MAY already have changed, so "nothing was installed"
        # would be a lie at that point. That includes the install cp ITSELF
        # - a sabotage that wraps just that one line back into this handler
        # is exactly what test_apply_install_cp_failure_never_claims_
        # nothing_was_installed below exists to catch. Post-install
        # failures have their own handling (the wazuh-analysisd -t check
        # and auto-rollback, and the install-cp-failure rollback below).
        try:
            print("2/6 Fetching current config", file=sys.stderr)
            scp_down(host, user, key, port, conf_path, tmp_current)
            with open(tmp_current, encoding="utf-8") as f:
                current = f.read()

            print("3/6 Building candidate config", file=sys.stderr)
            candidate = insert_block(current, block, anchor=args.anchor)
            with open(tmp_candidate, "w", encoding="utf-8") as f:
                f.write(candidate)

            print("4/6 Uploading candidate and checking XML well-formedness", file=sys.stderr)
            remote_candidate = _remote_scratch_path("candidate")
            scp_up(host, user, key, port, tmp_candidate, remote_candidate)
            # The candidate is a full ossec.conf, including any integration
            # API keys (office365, ms-graph, aws-s3, ...) - lock it down
            # explicitly rather than trust the remote session's umask, which
            # this local `scp` invocation never controls anyway (the remote
            # write happens inside the manager's own ssh session, not a
            # command line this script constructs).
            run_remote(host, user, key, port, f"chmod 600 {remote_candidate}")
            xml_check = run_remote(host, user, key, port, f"xmllint --noout {remote_candidate}", check=False)
            if xml_check.returncode != 0:
                sys.exit(_nothing_installed(
                    f"ABORTED - candidate is not well-formed XML.\n{xml_check.stderr}"))
        except KeyboardInterrupt:
            print(_nothing_installed("INTERRUPTED."), file=sys.stderr)
            raise
        except (RuntimeError, ValueError, OSError) as e:
            sys.exit(_nothing_installed(f"ABORTED - {e}"))

        print("5/6 Installing candidate and running Wazuh config test", file=sys.stderr)
        try:
            run_remote(host, user, key, port, f"sudo cp {remote_candidate} {conf_path}")
        except RuntimeError as install_error:
            # A failed `cp` can leave its DESTINATION truncated - cp opens
            # the destination for writing (and may truncate it) before it
            # is done reading the source, so a connection drop or a full
            # disk mid-copy can leave conf_path shorter than either the old
            # or the new config, not simply "unchanged". This must never
            # say "nothing was installed" - it attempts the same recovery
            # the wazuh-analysisd -t failure path below does, and names the
            # backup path either way.
            print(
                f"INSTALL FAILED - {install_error}\n"
                f"The live config at {conf_path} may be partially written "
                f"(a failed remote cp can truncate its destination). "
                f"Attempting rollback from the backup at {backup_path}...",
                file=sys.stderr,
            )
            try:
                run_remote(host, user, key, port, f"sudo cp {backup_path} {conf_path}")
            except RuntimeError as rollback_error:
                sys.exit(
                    f"INSTALL FAILED AND ROLLBACK FAILED - the live config at "
                    f"{conf_path} is in an UNKNOWN state (it may be partially "
                    f"written by the failed install). The backup is at "
                    f"{backup_path} on the manager - restore it by hand.\n"
                    f"Install error: {install_error}\nRollback error: {rollback_error}"
                )
            sys.exit(
                f"INSTALL FAILED, ROLLED BACK - {install_error}\n"
                f"The backup at {backup_path} was restored to {conf_path}."
            )

        test = run_remote(
            host, user, key, port,
            "sudo /var/ossec/bin/wazuh-analysisd -t 2>&1 || sudo /var/ossec/bin/ossec-analysisd -t 2>&1",
            check=False,
        )
        if test.returncode != 0:
            print(f"Config test FAILED, rolling back:\n{test.stdout}{test.stderr}", file=sys.stderr)
            run_remote(host, user, key, port, f"sudo cp {backup_path} {conf_path}")
            sys.exit("ROLLED BACK - the candidate config failed wazuh-analysisd -t. Backup restored.")

        print("6/6 Config test passed.", file=sys.stderr)
        if args.restart:
            print("Restarting wazuh-manager as requested...", file=sys.stderr)
            run_remote(host, user, key, port,
                       "sudo systemctl restart wazuh-manager"
                       " || sudo /var/ossec/bin/wazuh-control restart")
            print("Restarted.", file=sys.stderr)
        else:
            print(
                "Config is live but the manager was NOT restarted (pass --restart to apply it). "
                f"Backup of the prior config: {backup_path}",
                file=sys.stderr,
            )
    finally:
        _cleanup_scratch()


def cmd_rollback(args):
    host, user, key, port, conf_path = cfg()
    run_remote(host, user, key, port, f"sudo cp {args.backup} {conf_path}")
    print(f"Restored {args.backup} -> {conf_path}. Restart the manager to apply.")


def cmd_list_backups(args):
    host, user, key, port, conf_path = cfg()
    conf_dir = os.path.dirname(conf_path)
    conf_name = os.path.basename(conf_path)
    result = run_remote(host, user, key, port, f"ls -la {conf_dir}/{conf_name}.bak.* 2>/dev/null || true")
    print(result.stdout or "(no backups found)")


def main():
    p = argparse.ArgumentParser(description="Safe SSH editor for the Wazuh manager's ossec.conf")
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="Download the current ossec.conf")
    f.add_argument("--out", required=True)

    d = sub.add_parser("diff", help="Preview the diff of inserting a block (no changes made)")
    d.add_argument("--block", required=True, help="path to an XML fragment to insert")
    d.add_argument("--anchor", help="tag name to insert after (default: end of <ossec_config>)")

    a = sub.add_parser("apply", help="Backup, insert block, validate, install, optionally restart")
    a.add_argument("--block", required=True, help="path to an XML fragment to insert")
    a.add_argument("--anchor", help="tag name to insert after (default: end of <ossec_config>)")
    a.add_argument("--restart", action="store_true", help="restart wazuh-manager after a passing config test")

    r = sub.add_parser("rollback", help="Restore a specific backup file")
    r.add_argument("--backup", required=True, help="remote path to the .bak file to restore")

    sub.add_parser("list-backups", help="List ossec.conf.bak.* files on the manager")

    args = p.parse_args()
    try:
        {
            "fetch": cmd_fetch,
            "diff": cmd_diff,
            "apply": cmd_apply,
            "rollback": cmd_rollback,
            "list-backups": cmd_list_backups,
        }[args.cmd](args)
    except RuntimeError as e:
        sys.exit(f"ERROR: {e}")
    except ValueError as e:
        sys.exit(f"ERROR: {e}")
    except OSError as e:
        # A bad local path (--block, --out, ...) on any subcommand - not
        # just cmd_apply's own post-backup span, which additionally catches
        # this itself with backup-path messaging before it would ever reach
        # here.
        sys.exit(f"ERROR: {e}")


if __name__ == "__main__":
    main()
