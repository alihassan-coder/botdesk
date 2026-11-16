import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, CreatedAtMixin, IdMixin


class OAuthFlow(IdMixin, CreatedAtMixin, Base):
    """A sign-in with a provider that has started and not come back yet (ADR 0010 §5).

    One row per click on Connect, used once: the callback deletes it (`DELETE … RETURNING`) before
    anything else, so a state can never be replayed. The state itself is never stored, only its
    sha256; the PKCE verifier is encrypted with the credential vault's key. Rows live 10 minutes.
    """

    __tablename__ = "oauth_flows"

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))  # who clicked
    state_hash: Mapped[str] = mapped_column(String(64), unique=True)  # sha256 hex of the state
    code_verifier_encrypted: Mapped[str] = mapped_column(Text)
    connector_id: Mapped[str] = mapped_column(String(80))
    owner_kind: Mapped[str] = mapped_column(String(10))  # OwnerKind
    owner_bot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"))
    access: Mapped[str] = mapped_column(String(40))  # the scope set's key: "read", "full"
    scopes: Mapped[list[str]] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))  # as requested
    expires_at: Mapped[datetime] = mapped_column(index=True)
