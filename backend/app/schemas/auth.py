from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str = Field(min_length=10)


class AcceptInviteRequest(BaseModel):
    token: str
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=10)
    email: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10)


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
