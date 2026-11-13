from fastapi import APIRouter, status

from src.api.deps import AppSettings, Catalog, Db, OrgAccess, Secrets
from src.controllers import provider_controller
from src.schemas.provider import ModelListOut, ProviderKeyIn, ProviderOut, ProviderTestOut

router = APIRouter(prefix="/orgs/{org_id}", tags=["models and keys"])


@router.get("/providers")
async def list_providers(access: OrgAccess, db: Db, settings: AppSettings) -> list[ProviderOut]:
    """Every supported provider, whether it's connected, and the key's last 4 characters. Never the key."""
    return await provider_controller.list_providers(db, access, settings)


@router.put("/providers/{provider_id}")
async def save_key(
    provider_id: str, body: ProviderKeyIn, access: OrgAccess, db: Db, secrets: Secrets, catalog: Catalog
) -> ProviderOut:
    """Add or replace a key (owners and admins). `provider_id` is a built-in provider, "custom" for a
    new OpenAI-compatible server, or "custom-<id>" to change one. The key is checked live first."""
    return await provider_controller.save_key(db, access, provider_id, body, secrets=secrets, catalog=catalog)


@router.post("/providers/{provider_id}/test")
async def test_key(provider_id: str, access: OrgAccess, db: Db, secrets: Secrets, catalog: Catalog) -> ProviderTestOut:
    """Check a saved key again with a live call (owners and admins)."""
    return await provider_controller.test_key(db, access, provider_id, secrets=secrets, catalog=catalog)


@router.delete("/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_key(provider_id: str, access: OrgAccess, db: Db, catalog: Catalog) -> None:
    """Remove the organization's key (owners and admins). Its bots fall back to the server's key, if any."""
    await provider_controller.remove_key(db, access, provider_id, catalog=catalog)


@router.get("/models")
async def list_models(
    access: OrgAccess,
    db: Db,
    settings: AppSettings,
    secrets: Secrets,
    catalog: Catalog,
    provider: str | None = None,
    refresh: bool = False,
) -> ModelListOut:
    """The models every connected provider offers now (cached ~10 minutes; `refresh=true` asks again)."""
    return await provider_controller.list_models(
        db, access, provider=provider, refresh=refresh, settings=settings, secrets=secrets, catalog=catalog
    )
