"""The `! widens to` text for each guard (split out of crew_config.py, L-0725).

`crew_config._RATCHETED` pairs each guard with its rank, its normaliser and one
of these note tables. A write that widens a guard prints the note for the tier
it grants; every table is total over its guard's tiers, so a tier added without
a note is a KeyError where the note is printed rather than a grant described
by the wrong sentence.
"""
import crew_state


# What each guard actually governs, in the words the `! widens to` line reads
# out. Keyed on every member of `crew_state.GUARD_NAMES`, so a fifth guard
# added there is a KeyError below rather than a guard that widens with no note
# -- the same totality rule `_INSTALL_WIDENING_NOTES` carries, one level up.
GUARD_ACTIONS = {
    "terraformApply": "terraform/tofu apply and destroy, -chdir forms included",
    "forcePush": "git push --force / -f / --force-with-lease, and a "
                 "leading-plus refspec",
    "adminMerge": "gh pr merge --admin, which merges past a branch protection "
                  "rule somebody put there",
    "mergeGate": "taking a live repository's merge gate down and putting it "
                 "back, through /crew:gate",
    "prodDatabase": "a database matching a `production.databases` pattern",
    "prodServer": "a host matching a `production.hosts` pattern",
    "roleWrites": "a Write or Edit outside the calling role's declared scope, "
                  "per the policy table in "
                  "hooks/scripts/role_write_guard.py",
    "cloudDestructive": "aws delete-*/terminate-*/purge-*, s3 rm/rb and "
                        "sync --delete, az ... delete/purge, and Remove-Az*",
    "sqlDestructive": "DROP or TRUNCATE handed to psql, mysql, sqlcmd, "
                      "sqlite3 or Invoke-Sqlcmd, by flag, heredoc or pipe",
    "cloudGuard": "the Bash/PowerShell cloud guard's per-rule policies",
    "envGuard": "a Bash or PowerShell command that prints the whole process "
                "environment, or a credential-named variable, into the "
                "agent's context",
    "deployWorkflow": "a `gh workflow run` or `gh api .../dispatches` of a "
                      "workflow listed in `environments.workflows`",
}


def guard_widening_notes(name, what):
    """The `! widens to` note for one guard, total over `GUARD_POLICIES`.

    Total on purpose, `block` included: the CLI does `notes[granted]`, and a
    missing key there is a `KeyError` at the point of use rather than a warning
    that silently describes the wrong tier. That is the failure mode that
    produced `_INSTALL_WIDENING_NOTES`' own totality, and softening it here
    would reintroduce it for four keys at once.
    """
    return {
        "block": (
            f"crew refuses {what}. This is the narrowest policy and nothing "
            "widens into it."
        ),
        "ask": (
            f"crew will print the exact {what} command it was about to run "
            "and refuse until you approve THAT command by creating the marker "
            "file it names. The approval covers one command, not the guard: "
            "the next one asks again."
        ),
        "allow": (
            f"crew will run {what} WITHOUT asking. It still writes a row to "
            f"`{crew_state.GUARD_LOG_PATH}` saying what it let through, so "
            "the record exists - but nothing stops it at the time."
        ),
    }


def prod_widening_notes(name, what):
    """The `! widens to` note for one production guard, total over
    `PROD_LEVELS`.

    Total for the same reason `guard_widening_notes` is: the CLI indexes this
    with the tier being granted, so a missing key is a `KeyError` where a
    reader is being told what they just bought, rather than a note describing
    the wrong tier.
    """
    del name
    return {
        "none": (
            f"crew refuses every command aimed at {what}. This is the "
            "narrowest level and nothing widens into it."
        ),
        "read": (
            f"crew may run commands against {what} that it can POSITIVELY "
            "classify as read-only. Anything it cannot classify - an "
            "interactive session, an unrecognised tool, a command it cannot "
            "parse - is treated as a write and refused."
        ),
        "full": (
            f"crew may run ANY command against {what}, writes and deletes "
            f"included. Every one is recorded in `{crew_state.GUARD_LOG_PATH}`, "
            "so the record exists - but nothing stops it at the time."
        ),
    }


def role_write_widening_notes(name, what):
    """The `! widens to` note for `guards.roleWrites`, total over
    `crew_state.ROLE_WRITE_POLICIES`.

    Total for the same reason every other note table here is: the CLI does
    `notes[granted]`, and a missing key is a `KeyError` at the point of use
    rather than a note describing the wrong tier.

    Unlike `guard_widening_notes` and `prod_widening_notes`, the NARROWEST
    tier (`block`) is not this key's default -- `off` is, per CONFIG.md
    Sec18 and CLAUDE.md's rule that a hook which can block ships disabled.
    So the widening direction a reader most needs warned about is the same
    one every fresh repo already sits at: nothing narrows FROM `off`, because
    nothing narrower has been chosen yet.

    `off` and `report` both carry a Python caveat `block` does not need:
    only `role_write_guard.py` (Python) can actually evaluate this policy.
    `role-write-guard.sh`'s no-python fallback (its own "THE NO-PYTHON
    CONTRACT" comment) reads only the deny-list floor and fails CLOSED on a
    restricted role or one it cannot read at all -- so a repo set to `off`
    or `report` still gets `block`'s behaviour for a restricted role the
    moment python is unavailable. Printing `off`/`report` here with no
    mention of that would tell a reader those tiers apply unconditionally,
    which is the "unknown collapsing into the safe-looking value" shape
    CLAUDE.md names, worn the other way: not a guard that fails open, but a
    note that describes a WIDER guarantee than the fallback actually keeps.
    """
    del name
    return {
        "block": (
            f"crew refuses {what}. This is the narrowest policy and nothing "
            "widens into it."
        ),
        "report": (
            f"crew allows {what}, and appends a row to "
            f"`{crew_state.GUARD_LOG_PATH}` for every decision, not only "
            "the ones outside scope -- so the record exists, but nothing "
            "stops it at the time. Requires Python: without a usable "
            "interpreter, role-write-guard.sh/.ps1 cannot evaluate `report` "
            "at all and falls back to blocking a restricted role's write "
            "instead of logging it."
        ),
        "off": (
            f"crew's role-write guard does not run its policy check at all. "
            f"{what.capitalize()} is not refused and nothing is logged. "
            "This is the WIDEST tier and it is also the default -- every "
            "repo that has never set `guards.roleWrites` is already here. "
            "Requires Python: without a usable interpreter, the fallback "
            "cannot evaluate `off` either, so a restricted role's write is "
            "blocked anyway rather than let through."
        ),
    }


def cloud_guard_widening_notes(name, what):
    """The `! widens to` note for `guards.cloudGuard`, total over
    `crew_state.ROLE_WRITE_POLICIES` -- the vocabulary it shares with
    `roleWrites`, and the same split default (`off`) for the same reason.
    """
    del name
    return {
        "block": (
            f"crew enforces {what}: `block` denies, `ask` prompts (or denies "
            "when nobody is attending), `allow` lets through and logs. This is "
            "the narrowest tier and nothing widens into it."
        ),
        "report": (
            f"crew evaluates {what} and appends what it WOULD have done to "
            f"`{crew_state.GUARD_LOG_PATH}`, but refuses and prompts for "
            "nothing -- so the record exists, but nothing stops it at the time."
        ),
        "off": (
            "the cloud guard does not judge any command. This is the WIDEST "
            "tier and it is also the default -- every repo that has never set "
            "`guards.cloudGuard` is already here."
        ),
    }


def env_guard_widening_notes(name, what):
    """The `! widens to` note for `guards.envGuard`, total over
    `crew_state.ROLE_WRITE_POLICIES` -- `cloudGuard`'s vocabulary and split
    default (`off`), for the same reason (L-0772).
    """
    del name
    return {
        "block": (
            f"crew refuses {what}, and refuses a command it could not read "
            "well enough to tell. This is the narrowest tier and nothing "
            "widens into it."
        ),
        "report": (
            f"crew notes {what} in `{crew_state.GUARD_LOG_PATH}` (the rule "
            "and form, never the command or a value), but refuses nothing -- "
            "so the record exists, and the environment still reaches the "
            "agent's context."
        ),
        "off": (
            "the environment guard does not judge any command. This is the "
            "WIDEST tier and it is also the default -- every repo that has "
            "never set `guards.envGuard` is already here."
        ),
    }
