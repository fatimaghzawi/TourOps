from core.constants import AttachmentEntityType, UserRole

OPERATIONS_ROLES = (UserRole.TRAVEL_AGENT, UserRole.OWNER_ADMIN)
FINANCE_ROLES = (UserRole.ACCOUNTANT, UserRole.OWNER_ADMIN)
REPORT_ROLES = FINANCE_ROLES
OWNER_ROLES = (UserRole.OWNER_ADMIN,)
ALL_ROLES = (UserRole.TRAVEL_AGENT, UserRole.ACCOUNTANT, UserRole.OWNER_ADMIN)

OPS_ATTACHMENT_ENTITIES = frozenset(
    {
        AttachmentEntityType.CUSTOMERS.value,
        AttachmentEntityType.SUPPLIERS.value,
        AttachmentEntityType.BOOKINGS.value,
        AttachmentEntityType.PACKAGES.value,
        AttachmentEntityType.TOURS.value,
    }
)
FINANCE_ATTACHMENT_ENTITIES = frozenset(
    {
        AttachmentEntityType.EXPENSES.value,
        AttachmentEntityType.INVOICES.value,
        AttachmentEntityType.SUPPLIERS.value,
        AttachmentEntityType.BOOKINGS.value,
        AttachmentEntityType.CUSTOMERS.value,
    }
)

DASHBOARD_BY_ROLE = {
    UserRole.TRAVEL_AGENT.value: "dashboard:agent",
    UserRole.ACCOUNTANT.value: "dashboard:accountant",
    UserRole.OWNER_ADMIN.value: "dashboard:owner",
}


def role_values(*roles) -> set[str]:
    return {getattr(role, "value", role) for role in roles}


def user_role(request) -> str | None:
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return getattr(user, "role", None)


def has_role(request, *roles) -> bool:
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    return user.has_role(*roles)


def can_access_operations(request) -> bool:
    return has_role(request, *OPERATIONS_ROLES)


def can_access_finance(request) -> bool:
    return has_role(request, *FINANCE_ROLES)


def can_access_reports(request) -> bool:
    return has_role(request, *REPORT_ROLES)


def is_owner(request) -> bool:
    return has_role(request, *OWNER_ROLES)


def attachment_entities_for(role) -> frozenset[str]:
    value = getattr(role, "value", role)
    if value == UserRole.OWNER_ADMIN.value:
        return frozenset(item.value for item in AttachmentEntityType)
    if value == UserRole.TRAVEL_AGENT.value:
        return OPS_ATTACHMENT_ENTITIES
    if value == UserRole.ACCOUNTANT.value:
        return FINANCE_ATTACHMENT_ENTITIES
    return frozenset()


def can_use_attachment_entity(role, entity_type: str) -> bool:
    return (entity_type or "") in attachment_entities_for(role)


def dashboard_for_role(role: str) -> str:
    return DASHBOARD_BY_ROLE.get(role, "dashboard:home")
