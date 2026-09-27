"""Role → permission mapping. The only place that knows what each role may do."""

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    MEMBER = "member"


class Perm(StrEnum):
    CRM_READ = "crm:read"
    CRM_WRITE = "crm:write"
    CRM_DELETE = "crm:delete"
    PIPELINES_MANAGE = "pipelines:manage"
    MEMBERS_READ = "members:read"
    MEMBERS_MANAGE = "members:manage"
    ORG_MANAGE = "org:manage"
    ORG_DELETE = "org:delete"
    ORG_SECRETS = "org:secrets"  # API keys: owner only
    AUDIT_READ = "audit:read"


_MEMBER = {Perm.CRM_READ, Perm.CRM_WRITE, Perm.MEMBERS_READ}
_MANAGER = _MEMBER | {Perm.CRM_DELETE, Perm.PIPELINES_MANAGE}
_ADMIN = _MANAGER | {Perm.MEMBERS_MANAGE, Perm.ORG_MANAGE, Perm.AUDIT_READ}
_OWNER = _ADMIN | {Perm.ORG_DELETE, Perm.ORG_SECRETS}

ROLE_PERMISSIONS: dict[Role, frozenset[Perm]] = {
    Role.MEMBER: frozenset(_MEMBER),
    Role.MANAGER: frozenset(_MANAGER),
    Role.ADMIN: frozenset(_ADMIN),
    Role.OWNER: frozenset(_OWNER),
}

ROLE_RANK = {Role.MEMBER: 0, Role.MANAGER: 1, Role.ADMIN: 2, Role.OWNER: 3}


def permissions_for(role: Role) -> frozenset[Perm]:
    return ROLE_PERMISSIONS[role]
