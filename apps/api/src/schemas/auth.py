import uuid

from pydantic import EmailStr, Field, field_validator

from src.schemas.common import ApiModel
from src.schemas.organization import OrgOut

MIN_PASSWORD_LENGTH = 8


class SignUpIn(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)

    @field_validator("name")
    @classmethod
    def strip_name(cls, name: str) -> str:
        if not name.strip():
            raise ValueError("Tell us your name.")
        return name.strip()


class SignInIn(ApiModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ForgotPasswordIn(ApiModel):
    email: EmailStr


class UserOut(ApiModel):
    id: uuid.UUID
    name: str
    email: str
    handle: str


class MeOut(ApiModel):
    """Who is signed in, and which organizations they belong to."""

    user: UserOut
    organizations: list[OrgOut]


class MessageOut(ApiModel):
    message: str
