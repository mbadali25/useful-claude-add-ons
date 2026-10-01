"""crew-qa-standards' audit mutations, appended to `sabotage.py`'s MUTATIONS.
Kept apart only because `sabotage.py` sits at `.pylintrc`'s max-module-lines;
the runner, its restore guarantees and its reporting are all `sabotage.py`'s.
Run that file, not this one. Each was also run by hand and confirmed RED.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QA_AUDIT = os.path.join(CREW, "skills", "crew-qa-standards", "scripts", "qa_audit.py")
_T = "tests/test_qa_audit.py::"
# L-0529 / L-0531: the shared python-free bin fixture. Not a qa_audit mutation;
# it rides in this tuple because sabotage.py is at max-module-lines and this is
# the smallest sibling it already sums.
FIXTURES = os.path.join(CREW, "tests", "crew_fixtures.py")
_F = "tests/test_path_link_farm.py::"
# L-0516: the deadline polls that replaced fixed sleeps, and the ps1 tree kill
# the survivor poll proves. Here for the same max-module-lines reason.
POLL = os.path.join(CREW, "tests", "poll_fixtures.py")
_P = "tests/test_poll_fixtures.py::"
PS1_AUDIT = os.path.join(CREW, "hooks", "scripts", "completion-audit.ps1")
_E = "tests/test_event_claim_crash_safety.py::"

QA_AUDIT_MUTATIONS = (
    (
        # A pytest behind `make test` reads as a pass: "could not look" as
        # "looked and found nothing".
        "qa_audit reads an unfollowed CI wrapper as PASS",
        QA_AUDIT,
        '        return _row("H2", title, UNKNOWN, "tests exist but no CI line invokes pytest directly "\n',
        '        return _row("H2", title, PASS, "tests exist but no CI line invokes pytest directly "\n',
        _T + "test_h2_a_wrapper_it_cannot_follow_is_unknown_not_pass",
    ),
    (
        # `python -m pytest` read as a `-m pytest` marker subset again, which
        # hid the real Windows H3 gap on the audit's first run here.
        "qa_audit parses markers from the whole line again",
        QA_AUDIT,
        "    runs = [(w, _pytest_args(line)) for w, line in runs]\n",
        "",
        _T + "test_h3_python_dash_m_pytest_is_not_a_marker_selection",
    ),
    (
        # Only the signing pin is required; background maintenance goes unseen.
        "qa_audit stops requiring the maintenance pin",
        QA_AUDIT,
        'GIT_PINS = ("commit.gpgsign", "maintenance.auto")\n',
        'GIT_PINS = ("commit.gpgsign",)\n',
        _T + "test_h4_signing_pin_alone_still_names_maintenance",
    ),
    (
        # `-j 0` accepted: the setting that ran serially in a container.
        "qa_audit accepts pylint -j 0",
        QA_AUDIT,
        '           or re.search(r"(?:-j|--jobs)[\\s=]+[\\"\']?0\\b", line)]\n',
        "           or False]\n",
        _T + "test_h5_pylint_job_count[pylint -j 0 src/-GAP]",
    ),
    (
        # A check that raises is dropped instead of reported UNKNOWN.
        "qa_audit drops a check that raised",
        QA_AUDIT,
        '            rows.append(_row(check.__name__, check.__name__, UNKNOWN,\n',
        '            continue\n            rows.append(_row(check.__name__, check.__name__, UNKNOWN,\n',
        _T + "test_a_check_that_raises_is_unknown_not_dropped",
    ),
    (
        # A source dir reached through an alias (`/bin -> usr/bin`) is listed
        # and walked a second time.
        "link_path_dirs stops skipping a dir whose realpath was already linked",
        FIXTURES,
        "        if real in seen:\n            continue\n",
        "",
        _F + "test_a_dir_already_linked_through_an_alias_is_not_listed_again",
    ),
    (
        # `exists` follows the link, so a dangling entry reads as absent and
        # the same name is linked twice: the 36735895881 FileExistsError.
        "link_path_dirs checks a linked name with exists instead of lexists",
        FIXTURES,
        "            if skip(name) or os.path.lexists(target):\n",
        "            if skip(name) or os.path.exists(target):\n",
        _F + "test_a_dangling_entry_in_the_first_dir_still_shadows_the_same_name_later",
    ),
    (
        # One probe and out: the fixed-sleep shape again, minus the sleep.
        "poll_until probes once and never waits",
        POLL,
        "        if done(value) or time.monotonic() >= deadline:\n",
        "        if True:\n",
        _P + "test_poll_until_returns_once_a_late_child_has_died",
    ),
    (
        # At the deadline a falsy value of the probe's own type reads as
        # "nothing left": a real survivor passes as a success.
        "poll_until reports success at the deadline",
        POLL,
        "            return value\n",
        "            return value if done(value) else type(value)()\n",
        _P + "test_poll_until_reports_a_child_that_never_dies_at_the_deadline",
    ),
    (
        # An existing empty pidfile reads as pid 0: the exists()-only wait.
        "wait_for_pidfile accepts an existing empty file",
        POLL,
        "        return int(text) if text.isdigit() else None\n",
        "        return int(text) if text.isdigit() else 0\n",
        _P + "test_wait_for_pidfile_waits_past_an_empty_file_for_the_pid",
    ),
    (
        # Only the launcher dies; its python child outlives the probe.
        "the ps1 probe kills only the launcher",
        PS1_AUDIT,
        "            $proc.Kill($true)\n",
        "            $proc.Kill($false)\n",
        _E + "test_the_ps1_probe_timeout_kills_the_launchers_child_too",
    ),
)
