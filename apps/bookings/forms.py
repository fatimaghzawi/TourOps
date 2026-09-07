from django import forms

from apps.bookings.constants import FIELD_CLASS


def _styled(fields: dict[str, forms.Field]) -> None:
    for field in fields.values():
        existing = field.widget.attrs.get("class", "")
        classes = existing.split()
        if FIELD_CLASS not in classes:
            classes.append(FIELD_CLASS)
        field.widget.attrs["class"] = " ".join(dict.fromkeys(classes))


class BookingForm(forms.Form):
    customer_id = forms.ChoiceField(label="Customer")
    tour_id = forms.ChoiceField(label="Tour")
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, customer_choices=None, tour_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer_id"].choices = list(customer_choices or [])
        self.fields["tour_id"].choices = list(tour_choices or [])
        _styled(self.fields)
