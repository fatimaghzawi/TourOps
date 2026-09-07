from django.contrib.auth import login, logout
from django.contrib.auth.forms import PasswordResetForm
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.services import AUTH_BACKEND, AuthService, UserService, present_user
from core.access import OWNER_ROLES
from core.exceptions import TourOpsError
from core.http import actor_id, client_ip, guarded, json_body, method_view, resource_id
from core.responses import success_response


@require_http_methods(["POST"])
@guarded
def login_api(request):
    payload = json_body(request)
    user = AuthService().authenticate(
        payload.get("email") or "",
        payload.get("password") or "",
        ip=client_ip(request),
    )
    login(request, user, backend=AUTH_BACKEND)
    return success_response(present_user(user))


@require_POST
def logout_api(request):
    logout(request)
    return success_response({"signed_out": True})


@require_http_methods(["POST"])
@guarded
def password_reset(request):
    payload = json_body(request)
    form = PasswordResetForm({"email": payload.get("email") or ""})
    if form.is_valid():
        form.save(
            request=request,
            use_https=request.is_secure(),
            email_template_name="accounts/password_reset_email.html",
            subject_template_name="accounts/password_reset_subject.txt",
        )
    return success_response({"sent": True})


@guarded
def me(request):
    try:
        return success_response(UserService().get_presented(request.user.actor_id))
    except TourOpsError:
        return success_response(present_user(request.user))


@guarded
def list_users(request, **kwargs):
    return success_response({"users": UserService().list_users()})


@guarded
def create_user(request, **kwargs):
    payload = json_body(request)
    user = UserService().create_user(
        first_name=payload.get("first_name") or "",
        last_name=payload.get("last_name") or "",
        email=payload.get("email") or "",
        password=payload.get("password") or "",
        role=payload.get("role") or "",
        phone=payload.get("phone"),
        actor_id=actor_id(request),
    )
    return success_response(present_user(user), status=201)


@guarded
def get_user(request, **kwargs):
    return success_response(UserService().get_presented(resource_id(kwargs)))


@guarded
def set_status(request, **kwargs):
    payload = json_body(request)
    user = UserService().set_status(
        resource_id(kwargs),
        payload.get("status") or "",
        actor_id=actor_id(request),
    )
    return success_response(present_user(user))


@guarded
def change_role(request, **kwargs):
    payload = json_body(request)
    user = UserService().change_role(
        resource_id(kwargs),
        payload.get("role") or "",
        actor_id=actor_id(request),
    )
    return success_response(present_user(user))


@guarded
def reset_password(request, **kwargs):
    payload = json_body(request)
    user = UserService().reset_password(
        resource_id(kwargs),
        payload.get("password") or "",
        actor_id=actor_id(request),
    )
    return success_response(present_user(user))


users_collection = method_view(*OWNER_ROLES, GET=list_users, POST=create_user)
users_detail = method_view(*OWNER_ROLES, GET=get_user)
users_status = method_view(*OWNER_ROLES, POST=set_status)
users_role = method_view(*OWNER_ROLES, POST=change_role)
users_password = method_view(*OWNER_ROLES, POST=reset_password)
me_view = method_view(GET=me)
