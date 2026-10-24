import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slug import titlecase


def test_titlecase():
    assert titlecase("hello big world") == "Hello Big World"
