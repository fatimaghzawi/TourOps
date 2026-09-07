from __future__ import annotations

from django.core.cache import cache
from django.db import IntegrityError, transaction

from apps.accounts.constants import ROLE_LABELS
from apps.accounts.models import User
from apps.accounts.sessions import revoke_user_sessions
from apps.accounts.validators import normalize_email, validate_password
from apps.audit.constants import AuditAction
from apps.audit.services import safe_audit
from core.constants import UserRole, UserStatus
from core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from core.utils import full_name, utcnow

AUTH_BACKEND = "django.contrib.auth.backends.ModelBackend"
LOGIN_FAILURE_LIMIT = 8
LOGIN_LOCK_SECONDS = 15 * 60


def _login_keys(email: str, ip: str | None) -> list[str]:
    keys = [f"login-fail:email:{(email or '').strip().lower()}"]
    if ip:
        keys.append(f"login-fail:ip:{ip}")
    return keys


def _login_locked(email: str, ip: str | None) -> bool:
    return any((cache.get(key) or 0) >= LOGIN_FAILURE_LIMIT for key in _login_keys(email, ip))


def _record_login_failure(email: str, ip: str | None) -> None:
    for key in _login_keys(email, ip):
        cache.set(key, (cache.get(key) or 0) + 1, LOGIN_LOCK_SECONDS)


def _clear_login_failures(email: str, ip: str | None) -> None:
    cache.delete_many(_login_keys(email, ip))


def present_user(user: User | dict) -> dict:
    if isinstance(user, dict):
        first_name = user.get("first_name") or ""
        last_name = user.get("last_name") or ""
        email = user.get("email") or ""
        role = user.get("role")
        status = user.get("status")
        last_login = user.get("last_login_at") or user.get("last_login")
        user_id = str(user.get("id") or user.get("mongo_id") or user.get("_id") or "")
        phone = user.get("phone") or ""
        created_at = user.get("created_at")
        updated_at = user.get("updated_at")
    else:
        first_name = user.first_name
        last_name = user.last_name
        email = user.email
        role = user.role
        status = user.status
        last_login = user.last_login
        user_id = user.actor_id
        phone = user.phone or ""
        created_at = user.date_joined
        updated_at = None
    name = full_name(first_name, last_name) or email or "User"
    parts = [part for part in name.split() if part]
    initials = "".join(part[0] for part in parts[:2]).upper() or "U"
    if last_login and hasattr(last_login, "strftime"):
        last_display = last_login.strftime("%d %b %Y %H:%M")
    elif last_login:
        last_display = str(last_login)
    else:
        last_display = "Never"
    return {
        "id": user_id,
        "_id": user_id,
        "first_name": first_name,
        "last_name": last_name,
        "name": name,
        "initials": initials,
        "email": email,
        "phone": phone,
        "role": role,
        "role_label": ROLE_LABELS.get(role, role or ""),
        "status": status,
        "last": last_display,
        "last_login_at": last_login,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def user_to_document(user: User) -> dict:
    payload = user.as_actor_dict()
    payload["last_login_at"] = user.last_login
    payload["created_at"] = user.date_joined
    payload["updated_at"] = user.last_login
    return payload


class AuthService:
    def authenticate(self, email: str, password: str, *, ip: str | None = None) -> User:
        if not email or not password:
            raise ValidationError("Email and password are required.")
        if _login_locked(email, ip):
            raise PermissionDeniedError("Too many sign-in attempts. Try again in 15 minutes.")

        user = User.objects.filter(email=normalize_email(email)).first()
        if not user or not user.check_password(password):
            _record_login_failure(email, ip)
            raise ValidationError("Invalid email or password.")
        if not user.is_active:
            raise PermissionDeniedError("This account is inactive.")

        _clear_login_failures(email, ip)
        safe_audit(
            actor_id=user.actor_id,
            action=AuditAction.LOGIN.value,
            entity_type="users",
            entity_id=user.actor_id,
            description="Signed in.",
        )
        return user

    def change_password(self, user_id, current_password: str, new_password: str) -> User:
        user = UserService().get_user(user_id)
        if not user.check_password(current_password or ""):
            raise ValidationError("Current password is incorrect.")
        self._validate_new_password(new_password, user)
        if user.check_password(new_password):
            raise ValidationError("New password must be different from the current password.")
        user.set_password(new_password)
        user.save(update_fields=["password"])
        return user

    @staticmethod
    def _validate_new_password(new_password: str, user: User | None = None) -> None:
        validate_password(new_password)

    @staticmethod
    def hash_password(raw_password: str) -> str:
        from django.contrib.auth.hashers import make_password

        return make_password(raw_password)


class UserService:
    ALLOWED_ROLES = {item.value for item in UserRole}
    ALLOWED_STATUSES = {item.value for item in UserStatus}

    def list_users(self) -> list[dict]:
        return [present_user(user) for user in User.objects.all()]

    def get_user(self, user_id) -> User:
        user = User.objects.by_actor_id(user_id)
        if user is None and str(user_id).isdigit():
            user = User.objects.filter(pk=int(user_id)).first()
        if not user:
            raise NotFoundError("User not found.")
        return user

    def get_presented(self, user_id) -> dict:
        return present_user(self.get_user(user_id))

    def create_user(
        self,
        *,
        first_name: str,
        last_name: str,
        email: str,
        password: str,
        role: str,
        phone: str | None = None,
        actor_id=None,
    ) -> dict:
        first_name = (first_name or "").strip()
        last_name = (last_name or "").strip()
        email = normalize_email(email)
        phone = (phone or "").strip()
        if not first_name or not last_name:
            raise ValidationError("First name and last name are required.")
        if not email:
            raise ValidationError("Email is required.")
        if role not in self.ALLOWED_ROLES:
            raise ValidationError("Invalid role.")
        AuthService._validate_new_password(password)
        if User.objects.filter(email=email).exists():
            raise ValidationError("A user with this email already exists.")

        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    role=role,
                    phone=phone,
                    is_active=True,
                )
        except IntegrityError as extra:
            raise ValidationError("A user with this email already exists.") from extra

        safe_audit(
            actor_id=actor_id or user.actor_id,
            action=AuditAction.CREATED.value,
            entity_type="users",
            entity_id=user.actor_id,
            description=f"Created staff user {email} ({role}).",
            after={"email": email, "role": role},
        )
        return present_user(user)

    def set_status(self, user_id, status: str, *, actor_id) -> dict:
        if status not in self.ALLOWED_STATUSES:
            raise ValidationError("Invalid status.")
        user = self.get_user(user_id)
        if user.actor_id == str(actor_id) and status != UserStatus.ACTIVE.value:
            raise ValidationError("You cannot deactivate your own account.")
        if (
            user.role == UserRole.OWNER_ADMIN.value
            and status != UserStatus.ACTIVE.value
            and self._active_owner_count(exclude_id=user.pk) < 1
        ):
            raise ValidationError("Cannot deactivate the last Owner / Admin.")
        previous = user.status
        user.is_active = status == UserStatus.ACTIVE.value
        user.save(update_fields=["is_active"])
        if not user.is_active:
            revoke_user_sessions(user)
        safe_audit(
            actor_id=actor_id,
            action=AuditAction.STATUS_CHANGED.value,
            entity_type="users",
            entity_id=user.actor_id,
            description=f"Changed status for {user.email} to {status}.",
            before={"status": previous},
            after={"status": status},
        )
        return present_user(user)

    def change_role(self, user_id, role: str, *, actor_id) -> dict:
        if role not in self.ALLOWED_ROLES:
            raise ValidationError("Invalid role.")
        user = self.get_user(user_id)
        if user.actor_id == str(actor_id):
            raise ValidationError("You cannot change your own role.")
        if (
            user.role == UserRole.OWNER_ADMIN.value
            and role != UserRole.OWNER_ADMIN.value
            and self._active_owner_count(exclude_id=user.pk) < 1
        ):
            raise ValidationError("Cannot change the role of the last Owner / Admin.")
        previous = user.role
        user.role = role
        user.save()
        safe_audit(
            actor_id=actor_id,
            action=AuditAction.ROLE_CHANGED.value,
            entity_type="users",
            entity_id=user.actor_id,
            description=f"Changed role for {user.email} to {role}.",
            before={"role": previous},
            after={"role": role},
        )
        return present_user(user)

    def reset_password(self, user_id, new_password: str, *, actor_id) -> dict:
        user = self.get_user(user_id)
        if user.actor_id == str(actor_id):
            raise ValidationError("Use the change password form for your own account.")
        AuthService._validate_new_password(new_password, user)
        user.set_password(new_password)
        user.save(update_fields=["password"])
        return present_user(user)

    def _active_owner_count(self, exclude_id=None) -> int:
        query = User.objects.filter(role=UserRole.OWNER_ADMIN.value, is_active=True)
        if exclude_id is not None:
            query = query.exclude(pk=exclude_id)
        return query.count()
