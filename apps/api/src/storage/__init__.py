"""Where bots keep their files (ADR 0017 §3): one small interface, one adapter per kind of storage.

- `LocalStorage`: a folder on the BotDesk server.
- `S3Storage`: any S3-compatible service (AWS S3, Cloudflare R2, Backblaze B2, Tigris, MinIO…),
  signed with SigV4 and sent through the guarded HTTP client.

Adapters know nothing about bots, organizations or the database; `services/file_service.py` does.
"""

from src.storage.base import FileStorage, StorageError
from src.storage.local import LocalStorage
from src.storage.s3 import S3Location, S3Storage

__all__ = ["FileStorage", "LocalStorage", "S3Location", "S3Storage", "StorageError"]
