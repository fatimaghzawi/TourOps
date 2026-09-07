from decimal import Decimal

from django import forms

from apps.supplier_payments.constants import FIELD_CLASS, TRANSACTION_METHOD_CHOICES
from core.constants import DEFAULT_CURRENCY


def _styled(fields: dict[str, forms.Field]) -> None:
    for field in fields.values():
        existing = field.widget.attrs.get("class", "")
        classes = existing.split()
        if FIELD_CLASS not in classes:
            classes.append(FIELD_CLASS)
        field.widget.attrs["class"] = " ".join(dict.fromkeys(classes))


class SupplierPaymentForm(forms.Form):
    expense_id = forms.ChoiceField(label="Expense")
    amount = forms.DecimalField(
        min_value=Decimal("0.01"),
        decimal_places=2,
        max_digits=12,
        widget=forms.NumberInput(attrs={"step": "0.01"}),
    )
    payment_method = forms.ChoiceField(choices=TRANSACTION_METHOD_CHOICES, label="Method")
    payment_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d"],
        label="Payment date",
    )
    reference_number = forms.CharField(required=False, max_length=80, label="Transaction / reference number")
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    currency = forms.CharField(max_length=3, required=False, initial=DEFAULT_CURRENCY)

    def __init__(self, *args, expense_choices=None, lock_expense: bool = False, remaining=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["expense_id"].choices = list(expense_choices or [])
        if lock_expense:
            self.fields["expense_id"].widget = forms.HiddenInput()
        if remaining is not None:
            self.fields["amount"].widget.attrs["data-sp-amount"] = "true"
            self.fields["amount"].widget.attrs["data-max"] = str(remaining)
            self.fields["amount"].widget.attrs["max"] = str(remaining)
        self.fields["reference_number"].widget.attrs.setdefault(
            "placeholder", "Processor or bank transaction reference"
        )
        _styled(self.fields)
