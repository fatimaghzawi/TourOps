from django import forms

from apps.customers.constants import FIELD_CLASS


def _styled(fields: dict[str, forms.Field]) -> None:
    for field in fields.values():
        existing = field.widget.attrs.get("class", "")
        classes = existing.split()
        if FIELD_CLASS not in classes:
            classes.append(FIELD_CLASS)
        field.widget.attrs["class"] = " ".join(dict.fromkeys(classes))


class CustomerForm(forms.Form):
    first_name = forms.CharField(max_length=80)
    last_name = forms.CharField(max_length=80)
    email = forms.EmailField()
    phone = forms.CharField(required=False, max_length=40)
    city = forms.CharField(required=False, max_length=80)
    country = forms.CharField(required=False, max_length=80)
    passport = forms.CharField(required=False, max_length=40, label="Passport number")
    nationality = forms.CharField(required=False, max_length=80)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _styled(self.fields)
