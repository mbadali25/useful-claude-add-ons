"""Small text helpers."""

import re


def titlecase(text):
    return " ".join(word.capitalize() for word in text.split())


def slugify(text):
    if not isinstance(text, str):
        raise TypeError("text must be a str")
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
