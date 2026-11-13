"""Demo data for local development: `pnpm db:seed` (from the repo root).

Creates the same team the web app's mock uses, so the demo login works against the real API:
ali@acme.dev / botdesk123 (owner), sara@acme.dev (admin), omar@acme.dev (member), in "Acme Labs",
with three bots (Chief, Inbox Manager, Bug Fixer).
Safe to run more than once. Refuses to run in production.
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import security
from src.core.config import get_settings
from src.core.database import create_engine, create_sessionmaker
from src.models import Bot, Membership, Organization, User

DEMO_PASSWORD = "botdesk123"  # noqa: S105  (a published demo password, local only)
ORG = {"name": "Acme Labs", "slug": "acme-labs"}
BOTS = [
    ("Chief", "chief", "Chief of staff", "Coordinates the other bots and hands work to the right one.", "indigo"),
    ("Inbox Manager", "inbox-manager", "Email", "Sorts your inbox and drafts replies for approval.", "sky"),
    ("Bug Fixer", "bug-fixer", "Engineering", "Triages new issues and opens fix pull requests.", "rose"),
]
PEOPLE = [
    ("Ali Hassan", "ali@acme.dev", "ali", "owner"),
    ("Sara Khan", "sara@acme.dev", "sara", "admin"),
    ("Omar Farooq", "omar@acme.dev", "omar", "member"),
]


async def seed(db: AsyncSession) -> list[str]:
    """Add whatever is missing. Returns a line per thing created."""
    created = []
    org = await db.scalar(select(Organization).where(Organization.slug == ORG["slug"]))
    if org is None:
        org = Organization(**ORG)
        db.add(org)
        await db.flush()
        created.append(f"organization {ORG['name']}")

    for name, email, handle, role in PEOPLE:
        user = await db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(name=name, email=email, handle=handle, password_hash=security.hash_password(DEMO_PASSWORD))
            db.add(user)
            await db.flush()
            created.append(f"user {email}")
        if await db.get(Membership, (org.id, user.id)) is None:
            db.add(Membership(org_id=org.id, user_id=user.id, role=role))
            created.append(f"{email} as {role}")

    owner = await db.scalar(select(User).where(User.email == PEOPLE[0][1]))
    for name, handle, bot_role, description, color in BOTS:
        exists = await db.scalar(select(Bot.id).where(Bot.org_id == org.id, Bot.handle == handle))
        if exists is None:
            db.add(
                Bot(
                    org_id=org.id,
                    name=name,
                    handle=handle,
                    role=bot_role,
                    description=description,
                    avatar_color=color,
                    created_by=owner.id if owner else None,
                )
            )
            created.append(f"bot {name}")
    await db.commit()
    return created


async def main() -> None:
    settings = get_settings()
    if settings.is_production:
        raise SystemExit("Refusing to seed demo accounts in production.")
    engine = create_engine(settings.sqlalchemy_url)
    async with create_sessionmaker(engine)() as db:
        created = await seed(db)
    await engine.dispose()
    print("\n".join(f"+ {line}" for line in created) or "Demo data already there.")
    print(f"Sign in with ali@acme.dev / {DEMO_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
