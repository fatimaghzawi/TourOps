from django import forms

from apps.supplier_reservations.constants import FIELD_CLASS, STATUS_CHOICES


def _styled(fields: dict[str, forms.Field]) -> None:
    for field in fields.values():
        existing = field.widget.attrs.get("class", "")
        classes = existing.split()
        if FIELD_CLASS not in classes:
            classes.append(FIELD_CLASS)
        field.widget.attrs["class"] = " ".join(dict.fromkeys(classes))


class SupplierReservationForm(forms.Form):
    tour_id = forms.ChoiceField(label="Tour")
    supplier_id = forms.ChoiceField(label="Supplier")
    start_date = forms.DateField(
        required=False,
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
    release_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d"],
        label="Release / cutoff date",
    )
    confirmation_number = forms.CharField(required=False, max_length=80)
    quantity = forms.IntegerField(required=False, min_value=1, label="Quantity")
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    status = forms.ChoiceField(choices=STATUS_CHOICES, required=False)

    def __init__(self, *args, tour_choices=None, supplier_choices=None, lock_tour=False, lock_supplier=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tour_id"].choices = list(tour_choices or [])
        self.fields["supplier_id"].choices = list(supplier_choices or [])
        if lock_tour:
            self.fields["tour_id"].widget = forms.HiddenInput()
        if lock_supplier:
            self.fields["supplier_id"].widget = forms.HiddenInput()
        _styled(self.fields)


class ConfirmReservationForm(forms.Form):
    confirmation_number = forms.CharField(max_length=80, label="Confirmation number")
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}), label="Confirmation notes")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _styled(self.fields)


class SupplierEmailForm(forms.Form):
    kind = forms.ChoiceField(choices=())
    subject = forms.CharField(max_length=200)
    body = forms.CharField(widget=forms.Textarea(attrs={"rows": 16}))
    extra_note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Additional note")

    def __init__(self, *args, kind_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kind"].choices = list(kind_choices or [])
        _styled(self.fields)
