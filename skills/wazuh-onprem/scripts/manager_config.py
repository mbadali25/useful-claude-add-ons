#!/usr/bin/env python3
"""
manager_config.py — safe SSH-based editor for the Wazuh manager's ossec.conf.

Unlike wazuh_client.py (HTTP calls to the Server/Indexer/Dashboard APIs), this
talks to the manager host directly over SSH, because integrations, active
response, and log-source modules (office365, ms-graph, aws-s3, custom wodles)
are all configured in /var/ossec/etc/ossec.conf on disk — there is no API for
most of this on-prem.

IMPORTANT: this shells out to the local `ssh`/`scp` binaries. It only works if
the manager host is reachable from wherever this script runs and an SSH key is
authorized. In a sandboxed/agent environment with no route to the on-prem
network, these calls will simply fail to connect — that's expected; run the
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
import subprocess
import sys
import time

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


def _ssh_base(host, user, key, port):
    cmd = ["ssh", "-p", port, "-o", "StrictHostKeyChecking=accept-new"]
    if key:
        cmd += ["-i", key]
    cmd.append(f"{user}@{host}")
    return cmd


def _scp_base(key, port):
    cmd = ["scp", "-P", port, "-o", "StrictHostKeyChecking=accept-new"]
    if key:
        cmd += ["-i", key]
    return cmd


def run_remote(host, user, key, port, remote_cmd, check=True):
    """Run a command on the manager over SSH. remote_cmd is a shell string
    (built carefully by callers — no untrusted interpolation)."""
    full = _ssh_base(host, user, key, port) + [remote_cmd]
    result = subprocess.run(full, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(
            f"SSH command failed ({result.returncode}): {remote_cmd}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


def scp_down(host, user, key, port, remote_path, local_path):
    full = _scp_base(key, port) + [f"{user}@{host}:{remote_path}", local_path]
    result = subprocess.run(full, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"scp download failed: {result.stderr}")


def scp_up(host, user, key, port, local_path, remote_path):
    full = _scp_base(key, port) + [local_path, f"{user}@{host}:{remote_path}"]
    result = subprocess.run(full, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"scp upload failed: {result.stderr}")


def insert_block(current_xml, block_xml, anchor=None):
    """Insert `block_xml` into `current_xml`.

    Default: insert just before the closing </ossec_config> tag (the safe,
    generic anchor — every valid ossec.conf has exactly one). If `anchor` is
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
                "falling back to end-of-file insertion is safer — omit --anchor."
            )
        insert_at = idx + len(needle)
        return current_xml[:insert_at] + "\n\n  " + block_xml + current_xml[insert_at:]
    needle = "</ossec_config>"
    idx = current_xml.rfind(needle)
    if idx == -1:
        raise ValueError("No </ossec_config> closing tag found — is this a valid ossec.conf?")
    return current_xml[:idx] + "\n  " + block_xml + "\n" + current_xml[idx:]


def cmd_fetch(args):
    host, user, key, port, conf_path = cfg()
    scp_down(host, user, key, port, conf_path, args.out)
    print(f"Fetched {conf_path} -> {args.out}")


def cmd_diff(args):
    host, user, key, port, conf_path = cfg()
    tmp_current = "/tmp/_wazuh_current_ossec.conf"
    scp_down(host, user, key, port, conf_path, tmp_current)
    with open(tmp_current) as f:
        current = f.read()
    with open(args.block) as f:
        block = f.read()
    candidate = insert_block(current, block, anchor=args.anchor)
    diff = difflib.unified_diff(
        current.splitlines(keepends=True),
        candidate.splitlines(keepends=True),
        fromfile="current ossec.conf",
        tofile="candidate ossec.conf",
    )
    sys.stdout.writelines(diff)


def cmd_apply(args):
    host, user, key, port, conf_path = cfg()
    ts = time.strftime("%Y%m%d-%H%M%S")
    backup_path = f"{conf_path}.bak.{ts}"

    print(f"1/6 Backing up remote {conf_path} -> {backup_path}", file=sys.stderr)
    run_remote(host, user, key, port, f"sudo cp {conf_path} {backup_path}")

    print("2/6 Fetching current config", file=sys.stderr)
    tmp_current = "/tmp/_wazuh_current_ossec.conf"
    scp_down(host, user, key, port, conf_path, tmp_current)
    with open(tmp_current) as f:
        current = f.read()

    print("3/6 Building candidate config", file=sys.stderr)
    with open(args.block) as f:
        block = f.read()
    candidate = insert_block(current, block, anchor=args.anchor)
    tmp_candidate = "/tmp/_wazuh_candidate_ossec.conf"
    with open(tmp_candidate, "w") as f:
        f.write(candidate)

    print("4/6 Uploading candidate and checking XML well-formedness", file=sys.stderr)
    remote_candidate = "/tmp/_wazuh_candidate_ossec.conf"
    scp_up(host, user, key, port, tmp_candidate, remote_candidate)
    xml_check = run_remote(host, user, key, port, f"xmllint --noout {remote_candidate}", check=False)
    if xml_check.returncode != 0:
        sys.exit(f"ABORTED — candidate is not well-formed XML, nothing was touched:\n{xml_check.stderr}")

    print("5/6 Installing candidate and running Wazuh config test", file=sys.stderr)
    run_remote(host, user, key, port, f"sudo cp {remote_candidate} {conf_path}")
    test = run_remote(
        host, user, key, port,
        "sudo /var/ossec/bin/wazuh-analysisd -t 2>&1 || sudo /var/ossec/bin/ossec-analysisd -t 2>&1",
        check=False,
    )
    if test.returncode != 0:
        print(f"Config test FAILED, rolling back:\n{test.stdout}{test.stderr}", file=sys.stderr)
        run_remote(host, user, key, port, f"sudo cp {backup_path} {conf_path}")
        sys.exit("ROLLED BACK — the candidate config failed wazuh-analysisd -t. Backup restored.")

    print("6/6 Config test passed.", file=sys.stderr)
    if args.restart:
        print("Restarting wazuh-manager as requested...", file=sys.stderr)
        run_remote(host, user, key, port, "sudo systemctl restart wazuh-manager || sudo /var/ossec/bin/wazuh-control restart")
        print("Restarted.", file=sys.stderr)
    else:
        print(
            "Config is live but the manager was NOT restarted (pass --restart to apply it). "
            f"Backup of the prior config: {backup_path}",
            file=sys.stderr,
        )


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


if __name__ == "__main__":
    main()
