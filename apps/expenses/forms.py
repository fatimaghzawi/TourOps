from decimal import Decimal

from django import forms

from apps.expenses.constants import CATEGORY_CHOICES, FIELD_CLASS, SCOPE_CHOICES
from core.constants import DEFAULT_CURRENCY


def _styled(fields: dict[str, forms.Field]) -> None:
    for field in fields.values():
        existing = field.widget.attrs.get("class", "")
        classes = existing.split()
        if FIELD_CLASS not in classes:
            classes.append(FIELD_CLASS)
        field.widget.attrs["class"] = " ".join(dict.fromkeys(classes))


class ExpenseForm(forms.Form):
    expense_scope = forms.ChoiceField(choices=SCOPE_CHOICES, label="Scope")
    category = forms.ChoiceField(choices=CATEGORY_CHOICES)
    supplier_id = forms.ChoiceField(required=False, label="Supplier")
    tour_id = forms.ChoiceField(required=False, label="Related tour")
    amount = forms.DecimalField(
        min_value=Decimal("0.01"),
        decimal_places=2,
        max_digits=12,
        widget=forms.NumberInput(attrs={"step": "0.01"}),
    )
    currency = forms.CharField(max_length=3, required=False, initial=DEFAULT_CURRENCY)
    description = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))
    expense_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d"],
        label="Expense date",
    )
    due_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d"],
        label="Due date",
    )
    receipt_file = forms.CharField(required=False, max_length=255, label="Receipt / invoice file")

    def __init__(self, *args, supplier_choices=None, tour_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["supplier_id"].choices = [("", "Overhead (no supplier)")] + list(supplier_choices or [])
        self.fields["tour_id"].choices = [("", "General / not linked")] + list(tour_choices or [])
        self.fields["currency"].widget.attrs.setdefault("placeholder", DEFAULT_CURRENCY)
        _styled(self.fields)

    def clean_currency(self):
        value = (self.cleaned_data.get("currency") or DEFAULT_CURRENCY).strip().upper()
        return value or DEFAULT_CURRENCY

    def clean(self):
        cleaned = super().clean()
        scope = cleaned.get("expense_scope")
        tour_id = cleaned.get("tour_id")
        if scope == "TOUR" and not tour_id:
            self.add_error("tour_id", "Choose a tour for tour-scoped expenses.")
        if scope == "GENERAL":
            cleaned["tour_id"] = ""
        return cleaned
