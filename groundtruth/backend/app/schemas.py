"""Pydantic request/response schemas."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = ""
    anon_id: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    plan: str
    api_key: str
    subscription_status: str


class ExtractRequest(BaseModel):
    text: str = ""
    template: str = "custom"
    custom_fields: Optional[List[str]] = None
    model_id: Optional[str] = None


class CheckoutRequest(BaseModel):
    plan: str


class WaitlistRequest(BaseModel):
    email: EmailStr
    source: str = "landing"
    note: str = ""


class TrackRequest(BaseModel):
    name: str
    anon_id: str = ""
    meta: dict = Field(default_factory=dict)
