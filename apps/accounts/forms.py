from decimal import Decimal

from django import forms

from apps.accounts.constants import MIN_PASSWORD_LENGTH, ROLE_CHOICES
from apps.accounts.settings_service import PREFIX_SPECS
from core.constants import UserStatus

AUTH_INPUT_CLASS = (
    "w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-night "
    "placeholder:text-slate-400 shadow-sm outline-none transition "
    "focus:border-brand focus:ring-4 focus:ring-brand/15"
)


def _styled(fields: dict[str, forms.Field], *, auth: bool = False) -> None:
    for field in fields.values():
        existing = field.widget.attrs.get("class", "")
        classes = existing.split()
        if "field" not in classes:
            classes.append("field")
        if auth:
            classes.extend(AUTH_INPUT_CLASS.split())
        field.widget.attrs["class"] = " ".join(dict.fromkeys(classes))


def style_auth_form(form: forms.Form) -> None:
    _styled(form.fields, auth=True)
    email = form.fields.get("email")
    if email:
        email.widget.attrs.setdefault("placeholder", "you@agency.com")
        email.widget.attrs.update({"autocomplete": "username"})
    for name in ("new_password1", "new_password2", "new_password"):
        field = form.fields.get(name)
        if field:
            field.widget.attrs.update({"autocomplete": "new-password"})


class LoginForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"placeholder": "you@agency.com"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"placeholder": "••••••••"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _styled(self.fields, auth=True)
        self.fields["email"].widget.attrs.update({"autocomplete": "username"})
        self.fields["password"].widget.attrs.update({"autocomplete": "current-password"})


class StaffUserForm(forms.Form):
    first_name = forms.CharField(max_length=80)
    last_name = forms.CharField(max_length=80)
    email = forms.EmailField()
    phone = forms.CharField(max_length=40, required=False)
    role = forms.ChoiceField(choices=ROLE_CHOICES)
    password = forms.CharField(
        min_length=MIN_PASSWORD_LENGTH,
        widget=forms.PasswordInput,
    )
    confirm_password = forms.CharField(widget=forms.PasswordInput, label="Confirm password")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _styled(self.fields)
        self.fields["password"].widget.attrs.update({"autocomplete": "new-password"})
        self.fields["confirm_password"].widget.attrs.update({"autocomplete": "new-password"})

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        confirm = cleaned.get("confirm_password")
        if password and confirm and password != confirm:
            self.add_error("confirm_password", "Passwords do not match.")
        return cleaned


class ChangeRoleForm(forms.Form):
    role = forms.ChoiceField(choices=ROLE_CHOICES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _styled(self.fields)


class SetStatusForm(forms.Form):
    status = forms.ChoiceField(choices=[(item.value, item.value.title()) for item in UserStatus])


class ChangePasswordForm(forms.Form):
    current_password = forms.CharField(widget=forms.PasswordInput)
    new_password = forms.CharField(min_length=MIN_PASSWORD_LENGTH, widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput, label="Confirm new password")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _styled(self.fields)
        self.fields["current_password"].widget.attrs.update({"autocomplete": "current-password"})
        self.fields["new_password"].widget.attrs.update({"autocomplete": "new-password"})
        self.fields["confirm_password"].widget.attrs.update({"autocomplete": "new-password"})

    def clean(self):
        cleaned = super().clean()
        new_password = cleaned.get("new_password")
        confirm = cleaned.get("confirm_password")
        if new_password and confirm and new_password != confirm:
            self.add_error("confirm_password", "Passwords do not match.")
        return cleaned


class ResetPasswordForm(forms.Form):
    new_password = forms.CharField(min_length=MIN_PASSWORD_LENGTH, widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput, label="Confirm password")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _styled(self.fields)
        self.fields["new_password"].widget.attrs.update({"autocomplete": "new-password"})
        self.fields["confirm_password"].widget.attrs.update({"autocomplete": "new-password"})

    def clean(self):
        cleaned = super().clean()
        new_password = cleaned.get("new_password")
        confirm = cleaned.get("confirm_password")
        if new_password and confirm and new_password != confirm:
            self.add_error("confirm_password", "Passwords do not match.")
        return cleaned


class SystemSettingsForm(forms.Form):
    agency_name = forms.CharField(max_length=120, label="Agency name")
    legal_name = forms.CharField(max_length=160, required=False, label="Legal name")
    agency_email = forms.EmailField(required=False, label="Agency email")
    agency_phone = forms.CharField(max_length=40, required=False, label="Phone")
    agency_address = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}), label="Address")
    currency = forms.CharField(max_length=3, min_length=3, label="Currency")
    tax_name = forms.CharField(max_length=40, label="Tax name")
    tax_rate = forms.DecimalField(
        min_value=Decimal("0"),
        max_value=Decimal("100"),
        decimal_places=2,
        max_digits=5,
        label="Default tax %",
    )
    tax_enabled = forms.BooleanField(required=False, label="Charge tax by default")
    invoice_due_days = forms.IntegerField(min_value=1, max_value=120, label="Invoice due days")
    number_start = forms.IntegerField(min_value=1, max_value=999999, label="Numbering start")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for key, label, default in PREFIX_SPECS:
            self.fields[f"prefix_{key}"] = forms.CharField(
                max_length=8,
                label=label,
                initial=default,
            )
        _styled(self.fields)
        checkbox = self.fields["tax_enabled"].widget.attrs.get("class", "")
        self.fields["tax_enabled"].widget.attrs["class"] = " ".join(
            part for part in checkbox.split() if part != "field"
        )
        self.fields["currency"].widget.attrs.setdefault("placeholder", "USD")
        self.fields["agency_email"].widget.attrs.setdefault("placeholder", "hello@agency.com")

    def prefix_rows(self):
        rows = []
        for key, label, _default in PREFIX_SPECS:
            rows.append((label, self[f"prefix_{key}"]))
        return rows

    def clean_currency(self):
        value = (self.cleaned_data.get("currency") or "").strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise forms.ValidationError("Use a 3-letter currency code such as USD.")
        return value

    def clean(self):
        cleaned = super().clean()
        prefixes = {}
        for key, _label, _default in PREFIX_SPECS:
            name = f"prefix_{key}"
            value = (cleaned.get(name) or "").strip().upper()
            if not value:
                self.add_error(name, "Enter a prefix.")
            else:
                prefixes[key] = value
                cleaned[name] = value
        cleaned["prefixes"] = prefixes
        return cleaned

