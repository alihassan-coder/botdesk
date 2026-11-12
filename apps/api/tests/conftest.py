"""Each test gets a fresh app on an in-memory SQLite database, and an HTTP client for it.

No network and no Postgres needed, so the suite runs anywhere in a few seconds.
"""

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from src.core.config import Settings
from src.core.database import Base
from src.main import create_app

TEST_SETTINGS = Settings(environment="test", database_url="sqlite+aiosqlite://", _env_file=None)

PASSWORD = "correct-horse-battery"


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(TEST_SETTINGS)
    async with app.router.lifespan_context(app):
        async with app.state.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            yield http


async def sign_up(client: httpx.AsyncClient, name: str = "Ali Hassan", email: str = "ali@acme.dev") -> dict[str, Any]:
    response = await client.post("/api/v1/auth/sign-up", json={"name": name, "email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    me: dict[str, Any] = response.json()
    return me
