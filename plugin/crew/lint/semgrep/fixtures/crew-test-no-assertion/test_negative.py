import pytest


def check(name, condition):
    if not condition:
        raise SystemExit(name)


def test_asserts():
    assert 1 + 1 == 2


def test_raises():
    with pytest.raises(ValueError):
        int("x")


def test_check_helper():
    check("sum", 1 + 1 == 2)


def test_unittest_style(self):
    self.assertEqual(1, 1)


def test_must_not_raise():  # nosemgrep: crew-test-no-assertion
    len("abc")


def helper_not_a_test():
    return 1
