"""The T-0008 mutations: `crew_refresh_check.py`, the read-only check that
the code maps, diagrams and code graph a ticket's changes reach are current.
Same tuple shape as `sabotage.py`'s MUTATIONS -- (label, target, find,
replace, test) -- and appended to it there; `sabotage.py` sits near
`.pylintrc`'s max-module-lines, so this list lives apart. Run `sabotage.py`,
not this file.

Each one is a way the check could collapse an unknown or a stale artifact
into the pass the owner asked it never to give.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK = os.path.join(CREW, "hooks", "scripts", "crew_refresh_check.py")
_T = "tests/test_refresh_check.py::"

REFRESH_MUTATIONS = (
    ("the refresh check reports fresh whatever the artifacts say", CHECK,
     '    return {"status": overall, "reason": f"scope base {base[:12]} ({why})",\n',
     '    return {"status": FRESH, "reason": f"scope base {base[:12]} ({why})",\n',
     _T + "test_codemap_citing_changed_path_behind_is_stale"),
    ("an unknown artifact reads as fresh", CHECK,
     'UNKNOWN = "unknown"\n',
     'UNKNOWN = "fresh"\n',
     _T + "test_graphify_missing_is_unknown"),
    ("the freshness diff is <anchor>..HEAD, blind to an uncommitted edit", CHECK,
     '    return _git_lines(root, "diff", "--name-only", sha, "--", *paths)\n',
     '    return _git_lines(root, "diff", "--name-only", f"{sha}..HEAD", "--", *paths)\n',
     _T + "test_uncommitted_edit_in_cited_path_is_stale"),
)
