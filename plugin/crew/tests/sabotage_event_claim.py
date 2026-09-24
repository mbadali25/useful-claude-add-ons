"""Mutations for event_claim.py -- kept in a module of its own, same shape as
sabotage_autocycle.py, siblings of sabotage.py so that file stays under
`.pylintrc`'s max-module-lines rather than growing it again.

    python3 tests/sabotage_event_claim.py [--scratch DIR]
"""
import argparse
import filecmp
import os
import shutil
import subprocess
import sys
import tempfile

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(CREW, "hooks", "scripts")
EVENT_CLAIM = os.path.join(SCRIPTS, "event_claim.py")
_T = "tests/test_event_claim_crash_safety.py::"

EVENT_CLAIM_MUTATIONS = (
    # --- review round 3 (crew-1.0-r4-scope): mark_sent's read-then-write
    # TOCTOU -- a pruned-and-recycled generation could be stamped "sent"
    # under a stale token if the recycle landed between the nonce check and
    # the write. Reverts the nonce-keyed-marker fix back to the vulnerable
    # read/compare/temp-write/replace shape it replaced.
    ("mark_sent goes back to a read-then-write TOCTOU on a recycled generation",
     EVENT_CLAIM,
     '    nonce, _, path = token.partition(" ")\n'
     "    if not nonce or not path:\n"
     "        return False\n"
     "    try:\n"
     "        handle = os.open(_sent_marker(path, nonce), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)\n"
     "    except FileExistsError:\n"
     "        return True\n"
     "    except OSError:\n"
     "        return False\n"
     "    os.close(handle)\n"
     "    return True\n",
     '    nonce, _, path = token.partition(" ")\n'
     "    if not nonce or not path:\n"
     "        return False\n"
     "    try:\n"
     '        with open(path, "rb") as handle:\n'
     "            body = handle.read()\n"
     "    except OSError:\n"
     "        return False\n"
     "    try:\n"
     '        data = json.loads(body.decode("utf-8"))\n'
     '        at = float(data["at"])\n'
     '        stored_nonce = str(data["nonce"])\n'
     "    except (ValueError, KeyError, TypeError):\n"
     "        return False\n"
     "    if stored_nonce != nonce:\n"
     "        return False\n"
     '    temp = f"{path}.tmp-{nonce}"\n'
     "    try:\n"
     '        with open(temp, "wb") as handle:\n'
     '            handle.write(_record("sent", nonce, at))\n'
     "        os.replace(temp, path)\n"
     "    except OSError:\n"
     "        return False\n"
     "    return True\n",
     _T + "test_mark_sent_is_immune_to_a_prune_and_recreate_race_mid_call"),
    # --- Codex FIX (event_claim.py:215): a generation a pre-marker release
    # already sent, with "state":"sent" in the file body and no separate
    # marker, used to read back as "claimed" and get re-emitted after
    # upgrade. Reverts `_read` to checking only the marker.
    ("_read stops honouring a legacy in-file \"sent\" state with no marker",
     EVENT_CLAIM,
     '    except (ValueError, KeyError, TypeError):\n'
     '        return "claimed", mtime\n'
     '    if data.get("state") == "sent":\n'
     '        return "sent", at\n'
     "    if os.path.exists(_sent_marker(path, nonce)):\n",
     '    except (ValueError, KeyError, TypeError):\n'
     '        return "claimed", mtime\n'
     "    if os.path.exists(_sent_marker(path, nonce)):\n",
     _T + "test_a_legacy_sent_generation_with_no_marker_reads_as_sent"),
)


def run_test(target):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    done = subprocess.run([sys.executable, "-m", "pytest", target, "-q", "--no-header", "-x",
                           "-p", "no:cacheprovider", "--run-slow"],
                          cwd=CREW, capture_output=True, text=True, check=False, env=env)
    return done.returncode


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", default=None)
    args = parser.parse_args(argv)
    scratch = args.scratch or tempfile.mkdtemp(prefix="sabotage-event-claim-")
    os.makedirs(scratch, exist_ok=True)
    ok = True
    for index, (label, target, find, replace, test) in enumerate(EVENT_CLAIM_MUTATIONS):
        with open(target, encoding="utf-8", newline="") as handle:
            text = handle.read()
        if text.count(find) != 1:
            print(f"{'ANCHOR LOST':32} {label}")
            ok = False
            continue
        copy = os.path.join(scratch, f"{index:02d}-{os.path.basename(target)}")
        shutil.copyfile(target, copy)
        mutated = text.replace(find, replace)
        try:
            with open(target, "w", encoding="utf-8", newline="") as handle:
                handle.write(mutated)
            code = run_test(test)
        finally:
            shutil.copyfile(copy, target)
        if not filecmp.cmp(copy, target, shallow=False):
            print(f"RESTORE FAILED for {target} - the scratch copy is {copy}")
            return 3
        verdict = {0: "STILL GREEN - VACUOUS", 1: "RED (good)"}.get(code, f"RED BUT UNPROVEN - exit {code}")
        ok = ok and code == 1
        print(f"{verdict:32} {label}")
    print("\nEVENT_CLAIM SABOTAGE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
