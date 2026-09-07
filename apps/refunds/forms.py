from decimal import Decimal

from django import forms

from core.constants import PaymentMethod, RefundPolicyTier

FIELD_CLASS = "field"

TIER_CHOICES = (
    (RefundPolicyTier.DAYS_30_PLUS.value, "30+ days before departure — 90%"),
    (RefundPolicyTier.DAYS_15_TO_29.value, "15–29 days — 70%"),
    (RefundPolicyTier.DAYS_7_TO_14.value, "7–14 days — 50%"),
    (RefundPolicyTier.UNDER_7.value, "Under 7 days — no automatic refund"),
    (RefundPolicyTier.AGENCY_CANCEL.value, "Agency cancellation — 100%"),
    (RefundPolicyTier.OTHER.value, "Custom amount"),
)

METHOD_CHOICES = tuple((item.value, item.value.replace("_", " ").title()) for item in PaymentMethod)


def _styled(fields: dict[str, forms.Field]) -> None:
    for field in fields.values():
        if isinstance(field.widget, (forms.RadioSelect, forms.HiddenInput)):
            continue
        existing = field.widget.attrs.get("class", "")
        classes = existing.split()
        if FIELD_CLASS not in classes:
            classes.append(FIELD_CLASS)
        field.widget.attrs["class"] = " ".join(dict.fromkeys(classes))


class RefundRequestForm(forms.Form):
    payment_id = forms.ChoiceField(label="Payment")
    policy_tier = forms.ChoiceField(choices=TIER_CHOICES, widget=forms.RadioSelect, label="Policy")
    amount = forms.DecimalField(
        required=False,
        min_value=Decimal("0.01"),
        decimal_places=2,
        max_digits=12,
        widget=forms.NumberInput(attrs={"step": "0.01"}),
        label="Refund amount",
    )
    refund_method = forms.ChoiceField(choices=METHOD_CHOICES, label="Method")
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, payment_choices=None, lock_payment: bool = False, remaining=None, **kwargs):
        super().__init__(*args, **kwargs)
        choices = list(payment_choices or [])
        if lock_payment:
            self.fields["payment_id"].choices = choices
            self.fields["payment_id"].widget = forms.HiddenInput()
        else:
            self.fields["payment_id"].choices = [("", "Select a payment…")] + choices
        if remaining is not None:
            self.fields["amount"].widget.attrs["data-max"] = str(remaining)
        _styled(self.fields)

    def clean(self):
        cleaned = super().clean()
        tier = cleaned.get("policy_tier")
        amount = cleaned.get("amount")
        if tier == RefundPolicyTier.OTHER.value and amount is None:
            self.add_error("amount", "Enter the amount for a custom refund.")
        return cleaned
