"""Turn names into @handles and URL slugs, the same way the web app does."""

import re


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "untitled"


def make_handle(name: str, taken: set[str]) -> str:
    """`Release Notes` -> `release-notes`; adds -2, -3… if the handle is taken."""
    base = slugify(name)
    handle, n = base, 2
    while handle in taken:
        handle, n = f"{base}-{n}", n + 1
    return handle
