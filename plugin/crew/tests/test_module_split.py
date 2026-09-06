"""Invariants of the crew_state / crew_endpoints / crew_common split.

`crew_state` re-exports eight names so its callers did not have to change.
A re-export is a SECOND BINDING, not an alias: `crew_endpoints.read_endpoints`
looks `load_endpoints` up in `crew_endpoints`'s globals, so rebinding
`crew_state.load_endpoints` changes a name nothing reads. A test doing that
would run against the real function and pass while proving nothing -- the
guard failing open while wearing the label of a check that happened.

That is not a hypothesis. It is what happened to the 21 tests that patched
`crew_state.gizmoduck_installed`; they surfaced as AttributeError only because
`crew_state` does not re-export that name. The seven names it DOES re-export
have no such backstop, so this file is the backstop: a string-keyed patch of
any of them fails here, loudly, naming the module to patch instead.

Checked by AST rather than by grep so `setattr(crew_state , "read_text")` and
a line-wrapped call are caught the same as the canonical spelling.
"""
import ast
import os

import context  # noqa: F401  pylint: disable=unused-import
import crew_common
import crew_endpoints
import crew_state

_TESTS = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.join(os.path.dirname(_TESTS), "hooks", "scripts")


def _reexported():
    """Names `crew_state` imports from the two split modules, by reading it."""
    source = open(os.path.join(_SCRIPTS, "crew_state.py"),
                  encoding="utf-8").read()
    names = {}
    for node in ast.parse(source).body:
        if (isinstance(node, ast.ImportFrom)
                and node.module in ("crew_common", "crew_endpoints")):
            for alias in node.names:
                names[alias.asname or alias.name] = node.module
    return names


def _python_files():
    for directory in (_TESTS, _SCRIPTS):
        for name in sorted(os.listdir(directory)):
            if name.endswith(".py"):
                yield os.path.join(directory, name)


def test_crew_state_re_exports_exactly_what_its_callers_reach_for():
    """Every re-export resolves, and is the same object the owner defines.

    `is`, not a name check: an import that silently shadowed the owner's
    function with a different object would satisfy hasattr and still dispatch
    somewhere else.
    """
    owners = {"crew_common": crew_common, "crew_endpoints": crew_endpoints}
    reexported = _reexported()
    assert reexported, "crew_state imports from neither split module"
    for name, module in reexported.items():
        assert getattr(crew_state, name) is getattr(owners[module], name), (
            f"crew_state.{name} is not {module}.{name}")


def test_gizmoduck_installed_is_deliberately_not_re_exported():
    """The one name that MUST fail loudly when patched through crew_state.

    `read_endpoints` gates every finding on it, so a patch that silently
    stopped applying would let the endpoint tests run against the real
    detector and report a pass. Absent, `monkeypatch.setattr` raises.
    """
    assert not hasattr(crew_state, "gizmoduck_installed"), (
        "re-exporting this makes monkeypatch.setattr(crew_state, ...) succeed "
        "and do nothing; patch crew_endpoints instead")


def test_nothing_patches_a_re_exported_name_through_crew_state():
    """A string-keyed patch of a re-exported name is a silent no-op.

    It rebinds `crew_state`'s copy; the function that reads the name lives in
    the other module and never sees it. pytest cannot catch this -- the
    setattr succeeds -- so it is caught here instead.
    """
    reexported = _reexported()
    offenders = []
    for path in _python_files():
        if os.path.basename(path) == os.path.basename(__file__):
            continue
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "setattr"
                    and len(node.args) >= 2):
                continue
            target, attr = node.args[0], node.args[1]
            if not (isinstance(target, ast.Name)
                    and target.id == "crew_state"
                    and isinstance(attr, ast.Constant)
                    and attr.value in reexported):
                continue
            offenders.append(
                f"{os.path.basename(path)}:{node.lineno} patches "
                f"crew_state.{attr.value} -- patch "
                f"{reexported[attr.value]}.{attr.value} instead")
    assert not offenders, "\n".join(offenders)
