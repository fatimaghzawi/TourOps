from decimal import Decimal

from django import forms

from apps.packages.validators import join_list
from apps.tours.constants import FIELD_CLASS, STATUS_CHOICES
from core.constants import DEFAULT_CURRENCY, TourStatus


def _styled(fields: dict[str, forms.Field]) -> None:
    for field in fields.values():
        existing = field.widget.attrs.get("class", "")
        classes = existing.split()
        if FIELD_CLASS not in classes:
            classes.append(FIELD_CLASS)
        field.widget.attrs["class"] = " ".join(dict.fromkeys(classes))


class TourForm(forms.Form):
    package_id = forms.ChoiceField(label="Package")
    name = forms.CharField(required=False, max_length=200, label="Tour name")
    city = forms.CharField(required=False, max_length=80, label="Destination city")
    country = forms.CharField(required=False, max_length=80)
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d"],
        label="Start date",
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d"],
        label="End date",
    )
    capacity = forms.IntegerField(required=False, min_value=1)
    selling_price_per_person = forms.DecimalField(
        required=False,
        min_value=Decimal("0.01"),
        decimal_places=2,
        max_digits=12,
        label="Selling price / traveler",
        widget=forms.NumberInput(attrs={"step": "0.01"}),
    )
    currency = forms.CharField(max_length=3, required=False, initial=DEFAULT_CURRENCY)
    included_services = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Included")
    excluded_services = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Excluded")
    description = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    status = forms.ChoiceField(choices=STATUS_CHOICES, required=False)

    def __init__(self, *args, package_choices=None, include_status=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["package_id"].choices = [("", "Select a package")] + list(package_choices or [])
        if not include_status:
            self.fields.pop("status")
        else:
            self.fields["status"].initial = TourStatus.AVAILABLE.value
        self.fields["currency"].widget.attrs.setdefault("placeholder", DEFAULT_CURRENCY)
        self.fields["name"].widget.attrs.setdefault("placeholder", "Defaults to the package name")
        self.fields["package_id"].widget.attrs.setdefault("aria-required", "true")
        self.fields["start_date"].widget.attrs.setdefault("aria-required", "true")
        self.fields["capacity"].widget.attrs["data-cost-capacity"] = "1"
        self.fields["selling_price_per_person"].widget.attrs["data-cost-price"] = "1"
        _styled(self.fields)


def initial_from_tour(record: dict) -> dict:
    start = record.get("start_date")
    end = record.get("end_date")
    return {
        "name": record.get("name") or "",
        "package_id": record.get("package_id") or "",
        "city": record.get("city") or "",
        "country": record.get("country") or "",
        "start_date": start.date() if hasattr(start, "date") else start,
        "end_date": end.date() if hasattr(end, "date") else end,
        "capacity": record.get("capacity") or 1,
        "selling_price_per_person": record.get("price"),
        "currency": record.get("currency") or DEFAULT_CURRENCY,
        "included_services": join_list(record.get("included_services")),
        "excluded_services": join_list(record.get("excluded_services")),
        "description": record.get("description") or "",
        "status": record.get("status") or TourStatus.AVAILABLE.value,
    }


def initial_from_package(record: dict) -> dict:
    return {
        "name": record.get("name") or "",
        "package_id": record.get("id") or "",
        "city": record.get("city") or "",
        "country": record.get("country") or "",
        "capacity": record.get("default_capacity") or 1,
        "selling_price_per_person": record.get("price"),
        "currency": record.get("currency") or DEFAULT_CURRENCY,
        "included_services": join_list(record.get("included_services")),
        "excluded_services": join_list(record.get("excluded_services")),
        "description": record.get("description") or "",
    }
