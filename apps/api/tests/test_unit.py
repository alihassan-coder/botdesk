"""Small pure pieces: handles, password hashing, settings."""

from src.core import security
from src.core.config import Settings
from src.core.handles import make_handle, slugify


def test_slugify() -> None:
    assert slugify("Release Notes!") == "release-notes"
    assert slugify("  ") == "untitled"


def test_make_handle_avoids_taken_ones() -> None:
    assert make_handle("Ali", set()) == "ali"
    assert make_handle("Ali", {"ali", "ali-2"}) == "ali-3"


def test_passwords_hash_and_verify() -> None:
    hashed = security.hash_password("correct-horse")
    assert hashed != "correct-horse"
    assert security.verify_password(hashed, "correct-horse")
    assert not security.verify_password(hashed, "wrong-horse")
    assert not security.verify_password("not-a-hash", "correct-horse")


def test_tokens_are_stored_as_hashes() -> None:
    token = security.new_session_token()
    assert len(token) >= 40
    assert security.hash_token(token) != token
    assert security.hash_token(token) == security.hash_token(token)


def test_neon_urls_get_the_async_driver() -> None:
    settings = Settings(database_url="postgresql://u:p@host/db?sslmode=require", _env_file=None)
    assert settings.sqlalchemy_url == "postgresql+psycopg://u:p@host/db?sslmode=require"
    assert Settings(web_origins="http://a, http://b", _env_file=None).allowed_origins == ["http://a", "http://b"]


async def test_seed_creates_the_demo_team_once() -> None:
    from src.core.database import Base, create_engine, create_sessionmaker
    from src.seed import seed

    engine = create_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with create_sessionmaker(engine)() as db:
        first = await seed(db)
        again = await seed(db)
    await engine.dispose()
    assert "user ali@acme.dev" in first
    assert "sara@acme.dev as admin" in first
    assert "bot Chief" in first
    assert again == []
