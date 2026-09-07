from core.constants import UserRole

MIN_PASSWORD_LENGTH = 8

ROLE_LABELS = {
    UserRole.TRAVEL_AGENT.value: "Travel Agent",
    UserRole.ACCOUNTANT.value: "Accountant",
    UserRole.OWNER_ADMIN.value: "Owner / Admin",
}

ROLE_CHOICES = tuple((role.value, ROLE_LABELS[role.value]) for role in UserRole)
