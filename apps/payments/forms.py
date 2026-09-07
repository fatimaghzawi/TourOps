from django import forms

from core.constants import PaymentMethod

FIELD_CLASS = "field"

METHOD_CHOICES = tuple((item.value, item.value.replace("_", " ").title()) for item in PaymentMethod)


class PaymentForm(forms.Form):
    invoice_id = forms.ChoiceField(label="Invoice")
    amount = forms.DecimalField(min_value=0.01, decimal_places=2, max_digits=12)
    method = forms.ChoiceField(choices=METHOD_CHOICES)
    reference_number = forms.CharField(required=False, max_length=80)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, invoice_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["invoice_id"].choices = invoice_choices or []
        for field in self.fields.values():
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{css} {FIELD_CLASS}".strip()


class DeskPaymentForm(forms.Form):
    amount = forms.DecimalField(min_value=0.01, decimal_places=2, max_digits=12, label="Amount")
    method = forms.ChoiceField(choices=METHOD_CHOICES, label="Method")
    reference_number = forms.CharField(required=False, max_length=80, label="Reference")

    def __init__(self, *args, remaining=None, **kwargs):
        super().__init__(*args, **kwargs)
        if remaining is not None and not self.is_bound:
            self.fields["amount"].initial = remaining
        for field in self.fields.values():
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{css} {FIELD_CLASS}".strip()
        self.fields["amount"].widget.attrs["data-pay-amount"] = "1"
        if remaining is not None:
            self.fields["amount"].widget.attrs["data-max"] = str(remaining)
            self.fields["amount"].widget.attrs["step"] = "0.01"
