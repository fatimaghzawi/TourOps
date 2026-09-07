from django.urls import path

from apps.accounts import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("password/reset/", views.password_reset_view, name="password_reset"),
    path("password/reset/done/", views.StaffPasswordResetDoneView.as_view(), name="password_reset_done"),
    path(
        "password/reset/<uidb64>/<token>/",
        views.StaffPasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path("password/reset/complete/", views.password_reset_complete, name="password_reset_complete"),
    path("account/password/", views.change_password, name="password"),
    path("users/", views.users_list, name="users"),
    path("users/new/", views.user_create, name="user_create"),
    path("users/<str:id>/", views.user_detail, name="user_detail"),
    path("users/<str:id>/status/", views.user_set_status, name="user_status"),
    path("users/<str:id>/role/", views.user_change_role, name="user_role"),
    path("users/<str:id>/password/", views.user_reset_password, name="user_password"),
    path("settings/", views.settings_page, name="settings"),
]
