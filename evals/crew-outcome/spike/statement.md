Add a `slugify(text)` function to `slug.py`.

- It lowercases the text and replaces every run of characters that are not ASCII letters or digits with a single hyphen.
- It strips leading and trailing hyphens.
- `slugify("")` returns `""`.
- A `text` that is not a `str` raises `TypeError`.

Add tests for it in `tests/test_slug.py`. Keep `titlecase` working.
