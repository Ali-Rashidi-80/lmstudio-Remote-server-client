from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator


def _blank_email_to_none(v: str | None) -> str | None:
    if isinstance(v, str) and not v.strip():
        return None
    return v


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=10, max_length=256)


class AcceptInviteRequest(BaseModel):
    token: str = Field(min_length=8, max_length=256)
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=10, max_length=256)
    email: EmailStr | None = None

    _normalize_email = field_validator("email", mode="before")(_blank_email_to_none)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=10, max_length=256)


class UserOut(BaseModel):
    id: str
    username: str
    email: str | None
    role: str
    is_active: bool

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
