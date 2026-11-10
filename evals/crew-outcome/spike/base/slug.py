"""Small text helpers."""


def titlecase(text):
    return " ".join(word.capitalize() for word in text.split())
