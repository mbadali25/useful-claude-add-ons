"""crew_guards' production read list, reconciled with the env guard (L-0772).

A production host's environment holds that host's credentials, so printing it
is not a read `guards.prodServer: read` clears. BREAKING by narrowing.
"""
import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_guards

_PATTERNS = ["prod"]


@pytest.mark.parametrize("command", [
    "ssh prod printenv", "ssh prod env", "ssh prod cat /proc/1/environ",
    "ssh prod ps eww", "ssh prod 'echo $FAKE_TOKEN'"])
def test_environment_dumps_are_writes(command):
    assert crew_guards.classify_access(command) == "write"


@pytest.mark.parametrize("command", [
    "ssh prod env FOO=1 cat /etc/hosts", "ssh prod cat /etc/hosts",
    "ssh prod ps aux", "ssh prod 'echo $HOME'"])
def test_reads_stay_reads(command):
    assert crew_guards.classify_access(command) == "read"


@pytest.mark.parametrize("command", ["ssh prod printenv", "ssh prod env"])
def test_read_level_refuses_a_bare_environment_dump(command):
    assert crew_guards.prod_decision("read", command, _PATTERNS)[0] == "block"


def test_full_level_is_unchanged():
    assert crew_guards.prod_decision("full", "ssh prod env", _PATTERNS)[0] == "allow"


def test_printenv_is_off_the_read_list():
    assert "printenv" not in crew_guards.PROD_READ_COMMANDS
