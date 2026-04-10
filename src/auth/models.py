"""Pydantic models for auth domain objects."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class UserPublic(BaseModel):
    id: int
    username: str
    display_name: str | None = None
    email: str | None = None
    source: str = "local"
    is_active: bool = True


class PermissionNode(BaseModel):
    code: str
    name: str
    resource_type: str = "page"
    route_pattern: str | None = None
    component_id: str | None = None
    icon: str | None = None
    sort_order: int = 0
    description: str | None = None
    children: list[PermissionNode] = Field(default_factory=list)


class RoleSummary(BaseModel):
    id: int
    name: str
    description: str | None = None
    is_system: bool = False


class SessionRecord(BaseModel):
    id: str
    user_id: int
    created_at: datetime
    expires_at: datetime
    ip_address: str | None = None
    user_agent: str | None = None


class EffectivePermission(BaseModel):
    permission_id: int
    code: str
    can_view: bool = False
    can_edit: bool = False
    can_export: bool = False


class AuthContext(BaseModel):
    user: UserPublic
    roles: list[RoleSummary] = Field(default_factory=list)
    effective_by_code: dict[str, dict[str, Any]] = Field(default_factory=dict)
