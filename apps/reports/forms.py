from django import forms

from apps.reports.constants import FIELD_CLASS


def _styled(fields: dict[str, forms.Field]) -> None:
    for field in fields.values():
        existing = field.widget.attrs.get("class", "")
        classes = existing.split()
        if FIELD_CLASS not in classes:
            classes.append(FIELD_CLASS)
        field.widget.attrs["class"] = " ".join(dict.fromkeys(classes))


class ReportFilterForm(forms.Form):
    month = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"type": "month"}),
        label="Month",
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d"],
        label="From",
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d"],
        label="To",
    )
    tour_id = forms.ChoiceField(required=False, label="Tour")

    def __init__(self, *args, tour_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tour_id"].choices = [("", "All tours")] + list(tour_choices or [])
        _styled(self.fields)
