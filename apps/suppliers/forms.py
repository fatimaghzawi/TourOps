from django import forms

from apps.suppliers.constants import (
    CORE_TYPE_CHOICES,
    FIELD_CLASS,
    PREFERRED_METHOD_CHOICES,
    STATUS_CHOICES,
    TYPE_LABELS,
)
from apps.suppliers.validators import join_list


def _styled(fields: dict[str, forms.Field]) -> None:
    for field in fields.values():
        existing = field.widget.attrs.get("class", "")
        classes = existing.split()
        if FIELD_CLASS not in classes:
            classes.append(FIELD_CLASS)
        field.widget.attrs["class"] = " ".join(dict.fromkeys(classes))


class SupplierForm(forms.Form):
    name = forms.CharField(max_length=200, label="Company name")
    supplier_type = forms.ChoiceField(choices=CORE_TYPE_CHOICES, widget=forms.RadioSelect, label="Type")
    contact_person = forms.CharField(required=False, max_length=120, label="Contact")
    email = forms.EmailField(required=False)
    phone = forms.CharField(required=False, max_length=40)
    country = forms.CharField(required=False, max_length=80)
    city = forms.CharField(max_length=80, label="City")
    street = forms.CharField(required=False, max_length=200)
    tax_number = forms.CharField(required=False, max_length=80, label="Tax number")
    payment_terms = forms.CharField(required=False, max_length=80, label="Payment terms")
    preferred_payment_method = forms.ChoiceField(
        choices=PREFERRED_METHOD_CHOICES,
        widget=forms.RadioSelect,
        required=False,
        label="Preferred payment method",
    )
    bank_name = forms.CharField(required=False, max_length=120, label="Bank name")
    account_name = forms.CharField(required=False, max_length=120, label="Account holder name")
    iban = forms.CharField(required=False, max_length=80, label="IBAN")
    swift_bic = forms.CharField(required=False, max_length=40, label="SWIFT/BIC")
    account_number = forms.CharField(required=False, max_length=40, label="Account number")
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    status = forms.ChoiceField(choices=STATUS_CHOICES, required=False)

    star_rating = forms.IntegerField(required=False, min_value=0, max_value=5, label="Stars")

    vehicle_type = forms.CharField(required=False, max_length=80, label="Vehicle type")
    fleet_size = forms.IntegerField(required=False, min_value=0, label="Fleet size")
    seats_per_vehicle = forms.IntegerField(required=False, min_value=0, label="Seats / vehicle")
    license_number = forms.CharField(required=False, max_length=80, label="License number")
    coverage_areas = forms.CharField(required=False, label="Coverage areas")

    languages = forms.CharField(required=False)
    years_experience = forms.IntegerField(required=False, min_value=0, label="Years")
    specialties = forms.CharField(required=False)
    guide_license_number = forms.CharField(required=False, max_length=80, label="License number")

    iata_code = forms.CharField(required=False, max_length=8, label="IATA code")
    alliance = forms.CharField(required=False, max_length=80)

    activity_kinds = forms.CharField(required=False, label="Activity kinds")
    typical_duration_hours = forms.IntegerField(required=False, min_value=0, label="Typical duration (hours)")
    location = forms.CharField(required=False, max_length=120)

    cuisine = forms.CharField(required=False, max_length=80)
    seating_capacity = forms.IntegerField(required=False, min_value=0, label="Seating capacity")
    meal_types = forms.CharField(required=False, label="Meal types")

    policy_types = forms.CharField(required=False, label="Policy types")
    coverage_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Coverage notes")

    details = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, include_status=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not include_status:
            self.fields.pop("status")
        current = None
        if self.is_bound:
            current = (self.data.get("supplier_type") or "").strip()
        else:
            current = (self.initial.get("supplier_type") or "").strip()
        choices = list(CORE_TYPE_CHOICES)
        if current and current not in dict(CORE_TYPE_CHOICES):
            choices.append((current, TYPE_LABELS.get(current, current)))
        self.fields["supplier_type"].choices = choices
        self.fields["name"].widget.attrs.setdefault("placeholder", "Phoenicia Hotel")
        self.fields["name"].widget.attrs.setdefault("autocomplete", "organization")
        self.fields["contact_person"].widget.attrs.setdefault("autocomplete", "name")
        self.fields["email"].widget.attrs.setdefault("autocomplete", "email")
        self.fields["phone"].widget.attrs.setdefault("autocomplete", "tel")
        self.fields["phone"].widget.attrs.setdefault("inputmode", "tel")
        self.fields["city"].widget.attrs.setdefault("placeholder", "Beirut")
        self.fields["payment_terms"].widget.attrs.setdefault("placeholder", "Net 14")
        self.fields["bank_name"].widget.attrs.setdefault("placeholder", "Banque Misr")
        self.fields["account_name"].widget.attrs.setdefault("placeholder", "Nile View Hotel")
        self.fields["iban"].widget.attrs.setdefault("placeholder", "EG…")
        self.fields["swift_bic"].widget.attrs.setdefault("placeholder", "BMISEGCX")
        self.fields["languages"].widget.attrs.setdefault("placeholder", "Arabic, English")
        self.fields["specialties"].widget.attrs.setdefault("placeholder", "history, museums")
        for field in self.fields.values():
            if field.required:
                field.widget.attrs.setdefault("aria-required", "true")
        _styled(self.fields)


def initial_from_record(record: dict) -> dict:
    info = record.get("info") or {}
    address = record.get("address") or {}
    bank = record.get("bank_details") or {}
    return {
        "name": record.get("name") or "",
        "supplier_type": record.get("type") or record.get("supplier_type") or "",
        "contact_person": record.get("contact_person") or "",
        "email": record.get("email") or "",
        "phone": record.get("phone") or "",
        "country": record.get("country") or address.get("country") or "",
        "city": record.get("city") or address.get("city") or "",
        "street": record.get("street") or address.get("street") or "",
        "tax_number": record.get("tax_number") or "",
        "payment_terms": record.get("payment_terms") or "",
        "preferred_payment_method": record.get("preferred_payment_method") or "",
        "bank_name": bank.get("bank_name") or "",
        "account_name": bank.get("account_name") or "",
        "iban": bank.get("iban") or "",
        "swift_bic": bank.get("swift_bic") or "",
        "account_number": bank.get("account_number") or "",
        "notes": record.get("notes") or "",
        "status": record.get("status") or "",
        "star_rating": info.get("star_rating"),
        "vehicle_type": info.get("vehicle_type") or "",
        "fleet_size": info.get("fleet_size"),
        "seats_per_vehicle": info.get("seats_per_vehicle"),
        "license_number": info.get("license_number") or "",
        "coverage_areas": join_list(info.get("coverage_areas")),
        "languages": join_list(info.get("languages")),
        "years_experience": info.get("years_experience"),
        "specialties": join_list(info.get("specialties")),
        "guide_license_number": info.get("license_number") or "",
        "iata_code": info.get("iata_code") or "",
        "alliance": info.get("alliance") or "",
        "activity_kinds": join_list(info.get("activity_kinds")),
        "typical_duration_hours": info.get("typical_duration_hours"),
        "location": info.get("location") or "",
        "cuisine": info.get("cuisine") or "",
        "seating_capacity": info.get("seating_capacity"),
        "meal_types": join_list(info.get("meal_types")),
        "policy_types": join_list(info.get("policy_types")),
        "coverage_notes": info.get("coverage_notes") or "",
        "details": info.get("details") or "",
    }
