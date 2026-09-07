from django import forms

from apps.attachments.constants import CATEGORY_CHOICES, ENTITY_CHOICES, MAX_UPLOAD_BYTES

FIELD_CLASS = "field"


class AttachmentUploadForm(forms.Form):
    entity_type = forms.ChoiceField(choices=ENTITY_CHOICES, label="Record type")
    entity_id = forms.CharField(
        max_length=24,
        label="Record ID",
        widget=forms.TextInput(attrs={"placeholder": "24-character ID", "spellcheck": "false"}),
    )
    category = forms.ChoiceField(choices=CATEGORY_CHOICES, label="Category")
    notes = forms.CharField(
        required=False,
        max_length=200,
        label="Notes",
        widget=forms.TextInput(attrs={"placeholder": "Optional"}),
    )
    upload = forms.FileField(label="File")

    def __init__(self, *args, hide_entity: bool = False, allowed_entities=None, **kwargs):
        super().__init__(*args, **kwargs)
        if allowed_entities is not None:
            self.fields["entity_type"].choices = [
                (value, label) for value, label in ENTITY_CHOICES if value in allowed_entities
            ]
        if hide_entity:
            self.fields["entity_type"].widget = forms.HiddenInput()
            self.fields["entity_id"].widget = forms.HiddenInput()
        for field in self.fields.values():
            if isinstance(field.widget, forms.HiddenInput):
                continue
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} {FIELD_CLASS}".strip()

    def clean_upload(self):
        upload = self.cleaned_data.get("upload")
        if upload and getattr(upload, "size", 0) > MAX_UPLOAD_BYTES:
            raise forms.ValidationError("File is too large. Maximum size is 5 MB.")
        return upload
