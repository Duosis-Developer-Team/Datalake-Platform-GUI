"""Pydantic schemas for admin API request/response bodies."""

from __future__ import annotations

from pydantic import BaseModel, Field


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str | None = None
    email: str | None = None
    source: str
    is_active: bool
    roles: str = ""


class CreateUserRequest(BaseModel):
    username: str
    password: str
    display_name: str | None = None
    role_ids: list[int] = Field(default_factory=list)


class SetUserRolesRequest(BaseModel):
    role_ids: list[int]


class SetUserActiveRequest(BaseModel):
    is_active: bool


class RoleOut(BaseModel):
    id: int
    name: str
    description: str | None = None
    is_system: bool = False


class PermissionOut(BaseModel):
    id: int
    code: str
    name: str | None = None
    parent_id: int | None = None
    resource_type: str | None = None
    sort_order: int = 0
    is_dynamic: bool = False


class RolePermissionRow(BaseModel):
    permission_id: int
    can_view: bool
    can_edit: bool
    can_export: bool


class RoleMatrixRequest(BaseModel):
    triplets: list[tuple[int, bool, bool, bool]]


class CreatePermissionRequest(BaseModel):
    code: str
    name: str
    parent_code: str | None = None
    resource_type: str = "section"
    route_pattern: str | None = None


class TeamOut(BaseModel):
    id: int
    name: str
    parent_id: int | None = None
    created_by: int | None = None
    created_by_name: str | None = None
    member_count: int = 0


class CreateTeamRequest(BaseModel):
    name: str
    parent_id: int | None = None


class LdapConfigOut(BaseModel):
    id: int
    name: str
    server_primary: str
    server_secondary: str | None = None
    port: int
    use_ssl: bool
    bind_dn: str
    search_base_dn: str
    user_search_filter: str
    is_active: bool


class UpsertLdapRequest(BaseModel):
    ldap_id: int | None = None
    name: str = "default"
    server_primary: str
    server_secondary: str | None = None
    port: int = 389
    use_ssl: bool = False
    bind_dn: str
    bind_password: str | None = None
    search_base_dn: str
    user_search_filter: str = "(sAMAccountName={username})"
    is_active: bool = True


class LdapGroupMappingOut(BaseModel):
    id: int
    ldap_group_dn: str
    role_id: int
    role_name: str


class AddLdapMappingRequest(BaseModel):
    ldap_group_dn: str
    role_id: int


class AuditRow(BaseModel):
    id: int
    user_id: int | None = None
    username: str | None = None
    action: str
    detail: str | None = None
    ip_address: str | None = None
    created_at: str | None = None


# --- LDAP search & import ---


class LdapSearchResultUser(BaseModel):
    """One directory user returned by GET /ldap/search."""

    username: str
    display_name: str | None = None
    email: str | None = None
    distinguished_name: str


class LdapUserImportEntry(BaseModel):
    """Single AD user to import or upsert."""

    username: str
    distinguished_name: str
    display_name: str | None = None
    email: str | None = None


class ImportLdapUsersRequest(BaseModel):
    users: list[LdapUserImportEntry]
    role_ids: list[int] = Field(default_factory=list)
    team_ids: list[int] = Field(default_factory=list)


class UpdateUserRequest(BaseModel):
    display_name: str | None = None
    email: str | None = None


class SetUserTeamsRequest(BaseModel):
    team_ids: list[int]


class TeamMemberOut(BaseModel):
    user_id: int
    username: str
    display_name: str | None = None
    email: str | None = None


class AddTeamMembersRequest(BaseModel):
    user_ids: list[int]


class UpdateTeamRequest(BaseModel):
    name: str


class UpdateRoleRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class UserDetailOut(BaseModel):
    id: int
    username: str
    display_name: str | None = None
    email: str | None = None
    source: str
    is_active: bool
    roles: str = ""
    role_ids: list[int] = Field(default_factory=list)
    team_ids: list[int] = Field(default_factory=list)
