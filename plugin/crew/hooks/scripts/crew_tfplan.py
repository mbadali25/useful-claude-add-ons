"""Summarise a saved terraform/OpenTofu plan for crew's cloud guard.

    python3 crew_tfplan.py summarize PLANFILE [--chdir DIR]
                                    [--bin terraform|tofu] [--root DIR]

Writes `.crew/tfplan/<sha256 of the plan's bytes>.json`:

    {"plan", "workspace", "environment", "deletes": [address, ...],
     "tool", "created"}

`deletes` is every `resource_changes[].address` whose `change.actions`
contains `delete` -- a removal (`["delete"]`), a replacement
(`["delete","create"]` or `["create","delete"]`) and every resource of a
`-destroy` plan alike. `environment` is the plan's `environment` variable, or
null.

`workspace` is the workspace the PLAN is bound to, read out of the plan file
itself -- the same bytes the sha256 names -- and never from `workspace
show`, which answers for the directory at summarize time: a plan made under
`TF_WORKSPACE=production` in a directory whose selected workspace is
staging is a production plan, and terraform refuses to apply it anywhere
else. A saved plan is a zip whose `tfplan` member is the protobuf `Plan`;
its `backend` (field 13) carries `workspace` (field 3). Field numbers
measured on a terraform 1.16.3 plan (`tests/test_crew_tfplan.py`,
`REAL_PLAN`). When that cannot be read -- not a zip, no `tfplan` member, no
backend, no workspace, an empty one, an encrypted OpenTofu plan -- it is
null, and the cloud guard reads a null workspace as unknown and refuses.

WHY A SIDECAR. The cloud guard (`cloud_guard.py`) is a PreToolUse hook with a
15-second budget, so it cannot run `terraform show -json` itself -- and it
must not run terraform at all. It reads only the plan's bytes and this file.
The file is named by the sha256 of those bytes, taken BEFORE `show` runs and
checked again after it, so a plan changed after it was summarised has no
summary and its apply is treated as a possible destroy.

WHAT IT REFUSES, with exit 2 and nothing written: a `show` that exits
non-zero or times out (120s), output that is not a JSON object carrying a
`resource_changes` list whose every entry has an `actions` list, a plan
that is not a regular file or changed while it was being read, and a root
with no `.crew/` -- which this never creates. An earlier summary of the same plan
is left exactly as it was. A plan with no changes at all has no
`resource_changes` key (measured, terraform 1.16.3), so it is refused too;
its apply then asks, which is the direction to be wrong in.

The file is written to a temp file beside it and `os.replace`d into place.
"""
import argparse
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import zipfile

TIMEOUT = 120

# The cloud guard will not hash a plan bigger than this, so a summary of one
# would never be read.
PLAN_MAX_BYTES = 64 * 1024 * 1024


def _read_plan(path):
    """The plan's bytes, read once: the sha256 and the workspace both come
    from these same bytes. A FIFO or device is refused, not read."""
    if not stat.S_ISREG(os.stat(path).st_mode):
        raise OSError(f"{path} is not a regular file")
    with open(path, "rb") as handle:
        data = handle.read(PLAN_MAX_BYTES + 1)
    if len(data) > PLAN_MAX_BYTES:
        raise OSError(f"{path} is over 64 MiB")
    return data


def _sha256(path):
    return hashlib.sha256(_read_plan(path)).hexdigest()


def _varint(buf, index):
    shift = value = 0
    while True:
        if index >= len(buf) or shift > 63:
            raise ValueError("truncated varint")
        byte = buf[index]
        index += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, index
        shift += 7


def _fields(buf):
    """`[(number, payload)]` for every length-delimited field of a protobuf
    message; other wire types are skipped. Raises ValueError when `buf`
    is not a well-formed message."""
    out, index = [], 0
    while index < len(buf):
        key, index = _varint(buf, index)
        number, wire = key >> 3, key & 7
        if wire == 0:
            _value, index = _varint(buf, index)
        elif wire == 1:
            index += 8
        elif wire == 2:
            length, index = _varint(buf, index)
            if index + length > len(buf):
                raise ValueError("truncated field")
            out.append((number, buf[index:index + length]))
            index += length
        elif wire == 5:
            index += 4
        else:
            raise ValueError(f"wire type {wire}")
        if index > len(buf):
            raise ValueError("truncated field")
    return out


def plan_workspace(data):
    """The workspace the saved plan `data` is bound to, or None when it
    cannot be read. Never a guess: None is what the guard refuses on."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = archive.getinfo("tfplan")
            if info.file_size > PLAN_MAX_BYTES:
                return None
            with archive.open(info) as member:
                body = member.read(PLAN_MAX_BYTES + 1)
        backends = [p for n, p in _fields(body) if n == 13]
        if not backends:
            return None
        names = [p for n, p in _fields(backends[-1]) if n == 3]
        name = names[-1].decode("utf-8") if names else ""
    except (zipfile.BadZipFile, KeyError, ValueError, OSError, EOFError,
            RuntimeError, NotImplementedError, UnicodeDecodeError):
        return None
    return name or None


def _run(argv):
    return subprocess.run(argv, capture_output=True, timeout=TIMEOUT,
                          stdin=subprocess.DEVNULL, check=False)


def _deletes(doc):
    """The addresses `doc` deletes, or None when it cannot be read."""
    if not isinstance(doc, dict) or not isinstance(doc.get("resource_changes"),
                                                   list):
        return None
    out = []
    for change in doc["resource_changes"]:
        actions = change.get("change", {}).get("actions") \
            if isinstance(change, dict) and isinstance(change.get("change"),
                                                       dict) else None
        if not isinstance(actions, list):
            return None
        if "delete" in actions:
            out.append(str(change.get("address")))
    return out


def _environment(doc):
    variables = doc.get("variables")
    entry = variables.get("environment") if isinstance(variables, dict) \
        else None
    value = entry.get("value") if isinstance(entry, dict) else None
    return value if isinstance(value, str) else None


def summarize(plan, chdir=None, binary="terraform", root=None):
    """`(exit code, message)`. Writes the sidecar only on success."""
    root = root or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    crew_dir = os.path.join(root, ".crew")
    if not os.path.isdir(crew_dir):
        return 2, f"{crew_dir} does not exist, and crew_tfplan never creates it"
    exe = shutil.which(binary)
    if exe is None:
        return 2, f"`{binary}` is not on PATH"
    path = os.path.join(chdir, plan) if chdir else plan
    try:
        data = _read_plan(path)
    except OSError as exc:
        return 2, f"the plan {path} could not be read ({exc})"
    digest = hashlib.sha256(data).hexdigest()
    name = plan_workspace(data)
    base = [exe] + ([f"-chdir={chdir}"] if chdir else [])
    try:
        show = _run(base + ["show", "-json", plan])
    except (OSError, subprocess.SubprocessError) as exc:
        return 2, f"{binary} could not be run to completion ({type(exc).__name__})"
    if show.returncode != 0:
        return 2, f"`{binary} show -json {plan}` exited {show.returncode}"
    try:
        doc = json.loads(show.stdout.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return 2, f"`{binary} show -json` did not print JSON"
    deletes = _deletes(doc)
    if deletes is None:
        return 2, ("`show -json` printed no readable `resource_changes` "
                   "list, so what the plan deletes is not known")
    try:
        if _sha256(path) != digest:
            return 2, f"{path} changed while it was being summarised"
    except OSError as exc:
        return 2, f"the plan {path} could not be re-read ({type(exc).__name__})"
    record = {"plan": plan, "workspace": name,
              "environment": _environment(doc), "deletes": deletes,
              "tool": binary, "created": int(time.time())}
    text = json.dumps(record, indent=2) + "\n"
    folder = os.path.join(crew_dir, "tfplan")
    final = os.path.join(folder, digest + ".json")
    try:
        os.makedirs(folder, exist_ok=True)
        handle, temp = tempfile.mkstemp(dir=folder, prefix=".tmp-",
                                        suffix=".json")
        try:
            with os.fdopen(handle, "w", encoding="utf-8",
                           newline="\n") as out:
                out.write(text)
            os.replace(temp, final)
        except BaseException:
            try:
                os.unlink(temp)
            except OSError:
                pass
            raise
    except OSError as exc:
        return 2, f"{final} could not be written ({type(exc).__name__})"
    return 0, (f"wrote {final}: workspace {name}, "
               f"{len(deletes)} resource(s) deleted")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    summ = sub.add_parser("summarize", help="write the plan's sidecar")
    summ.add_argument("plan")
    summ.add_argument("--chdir", default=None)
    summ.add_argument("--bin", default="terraform")
    summ.add_argument("--root", default=None)
    args = parser.parse_args(argv)
    code, message = summarize(args.plan, args.chdir, args.bin, args.root)
    print(message, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
