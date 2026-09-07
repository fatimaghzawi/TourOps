from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.views import PasswordResetConfirmView, PasswordResetDoneView
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.forms import (
    ChangePasswordForm,
    ChangeRoleForm,
    LoginForm,
    ResetPasswordForm,
    StaffUserForm,
    SystemSettingsForm,
    style_auth_form,
)
from apps.accounts.services import AUTH_BACKEND, AuthService, UserService, present_user
from apps.accounts.settings_service import SettingsService, default_settings, initial_from_settings
from core.access import dashboard_for_role
from core.constants import UserRole, UserStatus
from core.exceptions import DatabaseUnavailableError, TourOpsError
from core.http import client_ip
from core.permissions import (
    login_required,
    role_required,
    safe_next_url,
)


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect(dashboard_for_role(request.user.role))

    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            user = AuthService().authenticate(
                form.cleaned_data["email"],
                form.cleaned_data["password"],
                ip=client_ip(request),
            )
        except TourOpsError as exc:
            messages.error(request, exc.message)
        else:
            login(request, user, backend=AUTH_BACKEND)
            messages.success(request, f"Welcome back, {user.first_name or user.email}.")
            next_url = safe_next_url(request, request.POST.get("next") or request.GET.get("next"))
            return redirect(next_url or reverse(dashboard_for_role(user.role)))

    return render(
        request,
        "accounts/login.html",
        {"form": form, "page_title": "Sign in", "next": request.GET.get("next") or request.POST.get("next") or ""},
    )


@require_http_methods(["GET", "POST"])
def logout_view(request):
    if request.method == "GET":
        if not request.user.is_authenticated:
            return redirect("accounts:login")
        return render(request, "accounts/logout.html", {"page_title": "Sign out"})
    logout(request)
    messages.success(request, "You have been signed out.")
    return redirect("accounts:login")


@require_http_methods(["GET", "POST"])
def password_reset_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:password")

    form = PasswordResetForm(request.POST or None)
    style_auth_form(form)
    if request.method == "POST" and form.is_valid():
        form.save(
            request=request,
            use_https=request.is_secure(),
            email_template_name="accounts/password_reset_email.html",
            subject_template_name="accounts/password_reset_subject.txt",
        )
        messages.success(
            request,
            "If that email is registered, we sent password reset instructions.",
        )
        return redirect("accounts:password_reset_done")

    return render(
        request,
        "accounts/password_reset.html",
        {"form": form, "page_title": "Reset password"},
    )


class StaffPasswordResetDoneView(PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"
    extra_context = {"page_title": "Check your email"}


class StaffPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")
    extra_context = {"page_title": "Choose a new password"}

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        style_auth_form(form)
        return form


@require_http_methods(["GET"])
def password_reset_complete(request):
    return render(
        request,
        "accounts/password_reset_complete.html",
        {"page_title": "Password updated"},
    )


@login_required
@require_http_methods(["GET", "POST"])
def change_password(request):
    form = ChangePasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            AuthService().change_password(
                request.user.actor_id,
                form.cleaned_data["current_password"],
                form.cleaned_data["new_password"],
            )
        except TourOpsError as exc:
            messages.error(request, exc.message)
        else:
            messages.success(request, "Your password has been updated.")
            return redirect("accounts:password")
    return render(
        request,
        "accounts/password.html",
        {"form": form, "page_title": "Change password", "page_heading": "Change password"},
    )


@login_required
@role_required(UserRole.OWNER_ADMIN)
def users_list(request):
    users = UserService().list_users()
    return render(
        request,
        "accounts/users.html",
        {"page_title": "Users", "page_heading": "Staff directory", "users": users},
    )


@login_required
@role_required(UserRole.OWNER_ADMIN)
@require_http_methods(["GET", "POST"])
def user_create(request):
    form = StaffUserForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            user = UserService().create_user(
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
                role=form.cleaned_data["role"],
                phone=form.cleaned_data["phone"],
                actor_id=request.user.actor_id,
            )
        except TourOpsError as exc:
            messages.error(request, exc.message)
        else:
            messages.success(request, f"Created {present_user(user)['name']}.")
            return redirect("accounts:user_detail", id=user["id"])
    return render(
        request,
        "accounts/user_form.html",
        {"form": form, "page_title": "New user", "page_heading": "Invite staff"},
    )


@login_required
@role_required(UserRole.OWNER_ADMIN)
@require_http_methods(["GET", "POST"])
def user_detail(request, id):
    service = UserService()
    try:
        record = service.get_presented(id)
    except TourOpsError:
        messages.error(request, "User not found.")
        return redirect("accounts:users")

    role_form = ChangeRoleForm(initial={"role": record["role"]})
    password_form = ResetPasswordForm()
    is_self = record["id"] == request.user.actor_id

    return render(
        request,
        "accounts/user_detail.html",
        {
            "page_title": record["name"],
            "page_heading": record["name"],
            "crumbs": [{"label": "Users", "url": reverse("accounts:users")}, {"label": record["name"], "url": ""}],
            "record": record,
            "role_form": role_form,
            "password_form": password_form,
            "is_self": is_self,
        },
    )


@login_required
@role_required(UserRole.OWNER_ADMIN)
@require_POST
def user_set_status(request, id):
    next_status = request.POST.get("status")
    try:
        UserService().set_status(id, next_status, actor_id=request.user.actor_id)
    except TourOpsError as exc:
        messages.error(request, exc.message)
    else:
        label = "activated" if next_status == UserStatus.ACTIVE.value else "deactivated"
        messages.success(request, f"User {label}.")
    return redirect("accounts:user_detail", id=id)


@login_required
@role_required(UserRole.OWNER_ADMIN)
@require_POST
def user_change_role(request, id):
    form = ChangeRoleForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Choose a valid role.")
        return redirect("accounts:user_detail", id=id)
    try:
        UserService().change_role(id, form.cleaned_data["role"], actor_id=request.user.actor_id)
    except TourOpsError as extra:
        messages.error(request, extra.message)
    else:
        messages.success(request, "Role updated.")
    return redirect("accounts:user_detail", id=id)


@login_required
@role_required(UserRole.OWNER_ADMIN)
@require_POST
def user_reset_password(request, id):
    form = ResetPasswordForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Passwords must match and be at least 8 characters.")
        return redirect("accounts:user_detail", id=id)
    try:
        UserService().reset_password(
            id,
            form.cleaned_data["new_password"],
            actor_id=request.user.actor_id,
        )
    except TourOpsError as extra:
        messages.error(request, extra.message)
    else:
        messages.success(request, "Password reset.")
    return redirect("accounts:user_detail", id=id)


@login_required
@role_required(UserRole.OWNER_ADMIN)
@require_http_methods(["GET", "POST"])
def settings_page(request):
    service = SettingsService()
    try:
        current = service.get()
    except DatabaseUnavailableError:
        messages.error(request, "Cannot reach MongoDB. Settings are unavailable.")
        current = default_settings()
    form = SystemSettingsForm(request.POST or None, initial=initial_from_settings(current))
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            service.update(
                actor_id=request.user.actor_id,
                agency_name=data["agency_name"],
                legal_name=data.get("legal_name"),
                agency_email=data.get("agency_email"),
                agency_phone=data.get("agency_phone"),
                agency_address=data.get("agency_address"),
                currency=data["currency"],
                tax_name=data["tax_name"],
                tax_rate=data["tax_rate"],
                tax_enabled=data.get("tax_enabled"),
                invoice_due_days=data["invoice_due_days"],
                number_start=data["number_start"],
                prefixes=data.get("prefixes"),
            )
        except DatabaseUnavailableError:
            messages.error(request, "Cannot reach MongoDB. Settings were not saved.")
        except TourOpsError as extra:
            messages.error(request, extra.message)
        else:
            messages.success(request, "Settings saved. New documents will use these values.")
            return redirect("accounts:settings")
    elif request.method == "POST":
        messages.error(request, "Check the settings and try again.")
    return render(
        request,
        "accounts/settings.html",
        {
            "form": form,
            "page_title": "Settings",
            "page_heading": "System settings",
        },
    )
