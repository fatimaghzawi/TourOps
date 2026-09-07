from decimal import Decimal

from django import forms

from apps.suppliers.constants import FIELD_CLASS, KIND_CHOICES, STATUS_CHOICES
from core.constants import CostBasis, DEFAULT_CURRENCY
from core.costing import BASIS_LABELS, default_cost_basis


def _styled(fields: dict[str, forms.Field]) -> None:
    for field in fields.values():
        existing = field.widget.attrs.get("class", "")
        classes = existing.split()
        if FIELD_CLASS not in classes:
            classes.append(FIELD_CLASS)
        field.widget.attrs["class"] = " ".join(dict.fromkeys(classes))


class SupplierOfferingForm(forms.Form):
    supplier_id = forms.ChoiceField(label="Supplier", required=False)
    name = forms.CharField(max_length=200, label="Service name")
    service_kind = forms.ChoiceField(choices=KIND_CHOICES, label="What it provides")
    estimated_cost = forms.DecimalField(
        required=False,
        min_value=Decimal("0.00"),
        decimal_places=2,
        max_digits=12,
        label="Typical cost (estimate)",
        widget=forms.NumberInput(attrs={"step": "0.01"}),
    )
    cost_basis = forms.ChoiceField(
        choices=tuple(BASIS_LABELS.items()),
        required=False,
        initial=CostBasis.PER_GROUP.value,
        label="How this cost is counted",
    )
    currency = forms.CharField(max_length=3, required=False, initial=DEFAULT_CURRENCY)
    description = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}), label="Notes for the agent")
    status = forms.ChoiceField(choices=STATUS_CHOICES, required=False)

    def __init__(self, *args, include_status=False, supplier_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not include_status:
            self.fields.pop("status")
        if supplier_choices is None:
            self.fields.pop("supplier_id")
        else:
            self.fields["supplier_id"].required = True
            self.fields["supplier_id"].choices = [("", "Select an existing supplier")] + list(supplier_choices)
        self.fields["name"].widget.attrs.setdefault("placeholder", "5-night accommodation")
        self.fields["name"].widget.attrs.setdefault("autocomplete", "off")
        self.fields["currency"].widget.attrs.setdefault("placeholder", DEFAULT_CURRENCY)
        self.fields["estimated_cost"].widget.attrs.setdefault("placeholder", "0.00")
        if not self.is_bound and not self.initial.get("cost_basis"):
            kind = self.initial.get("service_kind")
            self.fields["cost_basis"].initial = default_cost_basis(kind)
        if field := self.fields.get("supplier_id"):
            field.widget.attrs.setdefault("aria-required", "true")
        _styled(self.fields)
