from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from apps.accounts.models import User


class StaffUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email", "first_name", "last_name", "role", "phone")


class StaffUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = (
            "email",
            "first_name",
            "last_name",
            "phone",
            "role",
            "is_active",
            "password",
            "mongo_id",
            "last_login",
            "date_joined",
        )


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = StaffUserChangeForm
    add_form = StaffUserCreationForm
    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "role", "is_active", "last_login")
    list_filter = ("role", "is_active")
    search_fields = ("email", "first_name", "last_name", "phone")
    readonly_fields = ("mongo_id", "last_login", "date_joined", "is_staff", "is_superuser")
    date_hierarchy = "date_joined"
    filter_horizontal = ()

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("first_name", "last_name", "phone")}),
        ("Access", {"fields": ("role", "is_active")}),
        ("System", {"fields": ("mongo_id", "is_staff", "is_superuser", "last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "first_name", "last_name", "role", "phone", "password1", "password2"),
            },
        ),
    )
    actions = ("activate_users", "deactivate_users")

    @admin.action(description="Activate selected staff")
    def activate_users(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Activated {updated} user(s).")

    @admin.action(description="Deactivate selected staff")
    def deactivate_users(self, request, queryset):
        from apps.accounts.sessions import revoke_user_sessions

        to_disable = queryset.exclude(pk=request.user.pk)
        users = list(to_disable)
        updated = to_disable.update(is_active=False)
        for user in users:
            user.is_active = False
            revoke_user_sessions(user)
        self.message_user(request, f"Deactivated {updated} user(s).")


admin.site.site_header = "TourOps"
admin.site.site_title = "TourOps Admin"
admin.site.index_title = "System management"
