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


async def test_async_asserts():
    value = 1
    assert value == 1


def test_bare_raises_import():
    from pytest import raises

    with raises(ValueError):
        int("x")


def assert_blocked(name):
    if not name:
        raise SystemExit(name)


def test_helper_named_assert():
    assert_blocked("x")
