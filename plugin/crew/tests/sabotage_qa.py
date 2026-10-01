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
)
