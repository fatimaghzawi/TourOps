from django.urls import path

from apps.accounts import api

app_name = "accounts_api"

urlpatterns = [
    path("auth/login/", api.login_api, name="login"),
    path("auth/logout/", api.logout_api, name="logout"),
    path("auth/me/", api.me_view, name="me"),
    path("auth/password/reset/", api.password_reset, name="password_reset"),
    path("users/", api.users_collection, name="users"),
    path("users/<str:id>/", api.users_detail, name="user_detail"),
    path("users/<str:id>/status/", api.users_status, name="user_status"),
    path("users/<str:id>/role/", api.users_role, name="user_role"),
    path("users/<str:id>/password/", api.users_password, name="user_password"),
]
