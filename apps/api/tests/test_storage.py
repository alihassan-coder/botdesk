"""File storage adapters (ADR 0017 §3): Local on a temporary folder. S3-compatible storage needs a
network, so it is checked by hand (docs/testing/README.md); it shares this module's interface."""

from pathlib import Path

import pytest

from src.storage import LocalStorage, StorageError


async def test_local_storage_keeps_what_it_is_given(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "org")

    await storage.put("botdesk/inbox-manager/reports/march.csv", b"a,b\n1,2\n", content_type="text/csv")

    assert await storage.get("botdesk/inbox-manager/reports/march.csv") == b"a,b\n1,2\n"
    # A real folder people can open on the server.
    assert (tmp_path / "org" / "botdesk" / "inbox-manager" / "reports" / "march.csv").read_bytes() == b"a,b\n1,2\n"


async def test_local_storage_replaces_and_deletes(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    await storage.put("botdesk/a.txt", b"one", content_type="text/plain")
    await storage.put("botdesk/a.txt", b"two", content_type="text/plain")
    assert await storage.get("botdesk/a.txt") == b"two"

    await storage.delete("botdesk/a.txt")
    await storage.delete("botdesk/a.txt")  # already gone: fine

    with pytest.raises(StorageError, match="isn't there"):
        await storage.get("botdesk/a.txt")


@pytest.mark.parametrize("key", ["../escape.txt", "botdesk/../../escape.txt", "/etc/passwd", "C:/x.txt", ""])
async def test_local_storage_never_leaves_its_folder(tmp_path: Path, key: str) -> None:
    storage = LocalStorage(tmp_path / "org")
    with pytest.raises(StorageError):
        await storage.put(key, b"x", content_type="text/plain")
    assert not (tmp_path / "escape.txt").exists()


async def test_local_storage_check_says_it_works(tmp_path: Path) -> None:
    await LocalStorage(tmp_path / "new" / "org").check()  # creates its folder, writes, reads, deletes
