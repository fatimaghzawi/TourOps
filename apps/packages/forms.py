from decimal import Decimal

from django import forms

from apps.packages.constants import FIELD_CLASS, STATUS_CHOICES
from apps.packages.validators import join_list
from core.constants import DEFAULT_CURRENCY


def _styled(fields: dict[str, forms.Field]) -> None:
    for field in fields.values():
        existing = field.widget.attrs.get("class", "")
        classes = existing.split()
        if FIELD_CLASS not in classes:
            classes.append(FIELD_CLASS)
        field.widget.attrs["class"] = " ".join(dict.fromkeys(classes))


class PackageForm(forms.Form):
    name = forms.CharField(max_length=200, label="Package name")
    city = forms.CharField(max_length=80, label="City")
    country = forms.CharField(required=False, max_length=80)
    duration_days = forms.IntegerField(min_value=1, label="Duration (days)")
    selling_price_per_person = forms.DecimalField(
        required=False,
        min_value=Decimal("0.01"),
        decimal_places=2,
        max_digits=12,
        label="Selling price / person",
        widget=forms.NumberInput(attrs={"step": "0.01"}),
    )
    target_margin_percent = forms.DecimalField(
        required=False,
        min_value=Decimal("0.00"),
        max_value=Decimal("80.00"),
        decimal_places=2,
        max_digits=5,
        initial=Decimal("30.00"),
        label="Target margin %",
        widget=forms.NumberInput(attrs={"step": "0.5"}),
    )
    currency = forms.CharField(max_length=3, required=False, initial=DEFAULT_CURRENCY)
    default_capacity = forms.IntegerField(min_value=1, label="Default departure capacity")
    included_services = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Included",
    )
    excluded_services = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        label="Excluded",
    )
    description = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    status = forms.ChoiceField(choices=STATUS_CHOICES, required=False)

    def __init__(self, *args, include_status=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not include_status:
            self.fields.pop("status")
        self.fields["included_services"].widget.attrs.setdefault("placeholder", "Hotel, transfers, guided tour")
        self.fields["excluded_services"].widget.attrs.setdefault("placeholder", "Flights, personal expenses")
        self.fields["currency"].widget.attrs.setdefault("placeholder", DEFAULT_CURRENCY)
        self.fields["name"].widget.attrs.setdefault("placeholder", "Lebanon Discovery")
        self.fields["city"].widget.attrs.setdefault("placeholder", "Beirut")
        self.fields["default_capacity"].widget.attrs["data-cost-capacity"] = "1"
        self.fields["target_margin_percent"].widget.attrs["data-cost-margin"] = "1"
        self.fields["selling_price_per_person"].widget.attrs["data-cost-price"] = "1"
        self.fields["selling_price_per_person"].widget.attrs.setdefault("placeholder", "Leave blank to use suggested")
        for field in self.fields.values():
            if field.required:
                field.widget.attrs.setdefault("aria-required", "true")
        _styled(self.fields)


def initial_from_package(record: dict) -> dict:
    return {
        "name": record.get("name") or "",
        "city": record.get("city") or "",
        "country": record.get("country") or "",
        "duration_days": record.get("duration_days") or 1,
        "selling_price_per_person": record.get("price"),
        "target_margin_percent": record.get("target_margin_percent"),
        "currency": record.get("currency") or DEFAULT_CURRENCY,
        "default_capacity": record.get("default_capacity") or 1,
        "included_services": join_list(record.get("included_services")),
        "excluded_services": join_list(record.get("excluded_services")),
        "description": record.get("description") or "",
        "status": record.get("status") or "",
    }
