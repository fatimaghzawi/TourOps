from __future__ import annotations

from bson import ObjectId
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.accounts.constants import ROLE_LABELS
from core.constants import UserRole, UserStatus


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields):
        if not email:
            raise ValueError("Email is required.")
        email = self.normalize_email(email).strip().lower()
        extra_fields.setdefault("mongo_id", str(ObjectId()))
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("role", UserRole.TRAVEL_AGENT.value)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("role", UserRole.OWNER_ADMIN.value)
        extra_fields.setdefault("is_active", True)
        return self._create_user(email, password, **extra_fields)

    def active_with_roles(self, roles) -> models.QuerySet[User]:
        allowed = [getattr(role, "value", role) for role in roles]
        return self.filter(is_active=True, role__in=allowed)

    def by_actor_id(self, actor_id) -> User | None:
        if actor_id in (None, ""):
            return None
        return self.filter(mongo_id=str(actor_id)).first()


class User(AbstractUser):
    """Staff user stored in Django; mongo_id is the actor key used on Mongo documents."""

    username = None
    email = models.EmailField(unique=True)
    role = models.CharField(
        max_length=32,
        choices=[(item.value, ROLE_LABELS[item.value]) for item in UserRole],
        default=UserRole.TRAVEL_AGENT.value,
        db_index=True,
    )
    phone = models.CharField(max_length=40, blank=True)
    mongo_id = models.CharField(max_length=24, unique=True, db_index=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UserManager()

    class Meta:
        ordering = ["first_name", "last_name", "email"]
        verbose_name = "Staff user"
        verbose_name_plural = "Staff users"

    def save(self, *args, **kwargs):
        if not self.mongo_id:
            self.mongo_id = str(ObjectId())
        self.email = (self.email or "").strip().lower()
        is_owner = self.role == UserRole.OWNER_ADMIN.value
        self.is_staff = is_owner
        self.is_superuser = is_owner
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.get_full_name() or self.email

    @property
    def actor_id(self) -> str:
        return self.mongo_id

    @property
    def status(self) -> str:
        return UserStatus.ACTIVE.value if self.is_active else UserStatus.INACTIVE.value

    def has_role(self, *roles) -> bool:
        allowed = {getattr(role, "value", role) for role in roles}
        return self.role in allowed

    def as_actor_dict(self) -> dict:
        return {
            "_id": self.mongo_id,
            "id": self.mongo_id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "email": self.email,
            "role": self.role,
            "phone": self.phone,
            "status": self.status,
        }
