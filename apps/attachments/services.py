from __future__ import annotations

import mimetypes
import re
import uuid
from pathlib import Path

from django.conf import settings
from django.http import FileResponse
from pymongo.errors import PyMongoError

from apps.attachments.constants import (
    ALLOWED_CONTENT_TYPES,
    CATEGORY_LABELS,
    ENTITY_LABELS,
    IMAGE_CONTENT_TYPES,
    MAX_UPLOAD_BYTES,
    sniff_content_type,
)
from apps.attachments.repositories import AttachmentRepository
from apps.audit.constants import AuditAction
from apps.audit.services import safe_audit
from apps.notifications.constants import NotificationType
from apps.notifications.services import notify_for_type
from core.access import attachment_entities_for, can_use_attachment_entity
from core.constants import AttachmentCategory, AttachmentEntityType
from core.exceptions import DatabaseUnavailableError, NotFoundError, PermissionDeniedError, ValidationError
from core.soft_delete import stamp_new
from core.utils import parse_object_id, serialize_id, utcnow


def _iso(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "file").strip()) or "file"
    return cleaned[:120]


def present_attachment(document: dict) -> dict:
    category = document.get("category") or AttachmentCategory.OTHER.value
    entity_type = document.get("entity_type") or ""
    return {
        "id": serialize_id(document.get("_id")),
        "entity_type": entity_type,
        "entity_label": ENTITY_LABELS.get(entity_type, entity_type.replace("_", " ").title()),
        "entity_id": serialize_id(document.get("entity_id")),
        "category": category,
        "category_label": CATEGORY_LABELS.get(category, category.replace("_", " ").title()),
        "file_name": document.get("file_name") or "",
        "content_type": document.get("content_type") or "",
        "storage_key": document.get("storage_key") or "",
        "notes": document.get("notes") or "",
        "uploaded_by": serialize_id(document.get("uploaded_by")),
        "created_at": _iso(document.get("created_at")),
        "created_display": document.get("created_at").strftime("%d %b %Y %H:%M")
        if hasattr(document.get("created_at"), "strftime")
        else "—",
        "is_image": (document.get("content_type") or "").lower() in IMAGE_CONTENT_TYPES,
    }


class AttachmentService:
    def __init__(self, repository: AttachmentRepository | None = None):
        self.repository = repository or AttachmentRepository()

    def list_presented(self, **filters) -> list[dict]:
        return [present_attachment(row) for row in self.repository.list_items(**filters)]

    def list_presented_for_role(self, role, **filters) -> list[dict]:
        allowed = attachment_entities_for(role)
        entity_type = filters.get("entity_type")
        if entity_type:
            if entity_type not in allowed:
                return []
            return self.list_presented(**filters)
        return self.list_presented(**{**filters, "entity_types": list(allowed)})

    def assert_role_can_use(self, role, entity_type: str) -> None:
        if not can_use_attachment_entity(role, entity_type):
            raise PermissionDeniedError("You do not have permission to use files on this record.")

    def list_for_entity(self, entity_type: str, entity_id) -> list[dict]:
        return [present_attachment(row) for row in self.repository.list_for_entity(entity_type, entity_id)]

    def get(self, doc_id: str, *, actor_role=None) -> dict:
        try:
            document = self.repository.find_by_id(doc_id)
        except ValidationError as extra:
            raise NotFoundError("Attachment not found.") from extra
        if not document:
            raise NotFoundError("Attachment not found.")
        if actor_role is not None:
            self.assert_role_can_use(actor_role, document.get("entity_type") or "")
        return document

    def get_presented(self, doc_id: str, *, actor_role=None) -> dict:
        return present_attachment(self.get(doc_id, actor_role=actor_role))

    def absolute_path(self, storage_key: str) -> Path:
        root = Path(settings.MEDIA_ROOT)
        path = (root / storage_key).resolve()
        if not str(path).startswith(str(root.resolve())):
            raise ValidationError("Invalid storage key.")
        return path

    def file_response(self, doc_id: str, *, inline: bool = False, actor_role=None) -> FileResponse:
        document = self.get(doc_id, actor_role=actor_role)
        path = self.absolute_path(document.get("storage_key") or "")
        if not path.exists() or not path.is_file():
            raise NotFoundError("File is missing from storage.")
        response = FileResponse(
            path.open("rb"),
            as_attachment=not inline,
            filename=document.get("file_name") or "attachment",
            content_type=document.get("content_type") or "application/octet-stream",
        )
        response["X-Content-Type-Options"] = "nosniff"
        if inline and (document.get("content_type") or "") not in IMAGE_CONTENT_TYPES:
            response["Content-Disposition"] = f'attachment; filename="{document.get("file_name") or "attachment"}"'
        return response

    def gallery_for_tours(self, tour_ids) -> dict[str, list[dict]]:
        grouped: dict[str, list[dict]] = {}
        if not tour_ids:
            return grouped
        wanted = {str(item) for item in tour_ids if item}
        for row in self.list_presented(
            entity_type=AttachmentEntityType.TOURS.value,
            category=AttachmentCategory.GALLERY.value,
        ):
            if not row.get("is_image"):
                continue
            entity_id = row.get("entity_id")
            if entity_id not in wanted:
                continue
            grouped.setdefault(entity_id, []).append(row)
        for photos in grouped.values():
            photos.reverse()
        return grouped

    def create(
        self,
        *,
        actor_id,
        entity_type: str,
        entity_id,
        category: str,
        upload,
        notes: str | None = None,
        actor_role=None,
    ) -> dict:
        entity_type = (entity_type or "").strip()
        category = (category or "").strip().upper()
        if actor_role is not None:
            self.assert_role_can_use(actor_role, entity_type)
        if entity_type not in {item.value for item in AttachmentEntityType}:
            raise ValidationError("Invalid entity type.")
        if category not in {item.value for item in AttachmentCategory}:
            raise ValidationError("Invalid category.")
        if upload is None:
            raise ValidationError("A file is required.")

        file_name = _safe_name(getattr(upload, "name", "") or "file")
        content_type = (getattr(upload, "content_type", None) or "").lower()
        if content_type not in ALLOWED_CONTENT_TYPES:
            guessed = (mimetypes.guess_type(file_name)[0] or "").lower()
            if guessed in ALLOWED_CONTENT_TYPES:
                content_type = guessed
        size = int(getattr(upload, "size", 0) or 0)
        if size <= 0:
            raise ValidationError("Uploaded file is empty.")
        if size > MAX_UPLOAD_BYTES:
            raise ValidationError("File is too large. Maximum size is 5 MB.")
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise ValidationError("Unsupported file type.")

        header = b""
        if hasattr(upload, "read"):
            header = upload.read(16) or b""
            if hasattr(upload, "seek"):
                try:
                    upload.seek(0)
                except Exception:
                    pass
        detected = sniff_content_type(header)
        if detected:
            content_type = detected
        elif content_type == "text/plain" and b"\x00" not in header:
            content_type = "text/plain"
        else:
            raise ValidationError("File contents do not match a supported type.")
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise ValidationError("Unsupported file type.")

        storage_key = f"attachments/{entity_type}/{entity_id}/{uuid.uuid4().hex}_{file_name}"
        dest = self.absolute_path(storage_key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as handle:
            for chunk in upload.chunks():
                handle.write(chunk)

        document = stamp_new(
            {
                "entity_type": entity_type,
                "entity_id": parse_object_id(entity_id, field="entity_id"),
                "category": category,
                "file_name": file_name,
                "content_type": content_type,
                "storage_key": storage_key,
                "notes": (notes or "").strip() or None,
                "uploaded_by": parse_object_id(actor_id, field="uploaded_by"),
                "created_at": utcnow(),
            }
        )
        try:
            result = self.repository.insert(document)
        except PyMongoError as extra:
            dest.unlink(missing_ok=True)
            raise DatabaseUnavailableError("Could not save the attachment.") from extra
        document["_id"] = result.inserted_id
        saved = self.get(document["_id"])
        presented = present_attachment(saved)
        safe_audit(
            actor_id=actor_id,
            action=AuditAction.UPLOADED.value,
            entity_type="attachments",
            entity_id=saved["_id"],
            description=f"Uploaded {presented['file_name']} to {presented['entity_label'].lower()} {presented['entity_id']}.",
            after={"file_name": presented["file_name"], "entity_type": entity_type, "category": category},
        )
        notify_for_type(
            NotificationType.ATTACHMENT.value,
            title="Document uploaded",
            message=f"{presented['file_name']} was attached to {presented['entity_label'].lower()} {presented['entity_id']}.",
            related_entity_type=entity_type,
            related_entity_id=presented["entity_id"],
            exclude_user_id=actor_id,
        )
        return saved

    def soft_delete(self, doc_id, *, actor_id, actor_role=None) -> None:
        document = self.get(doc_id, actor_role=actor_role)
        try:
            result = self.repository.soft_delete(document["_id"], actor_id)
        except PyMongoError as extra:
            raise DatabaseUnavailableError("Could not delete the attachment.") from extra
        if result.matched_count != 1:
            raise NotFoundError("Attachment not found.")
        presented = present_attachment(document)
        safe_audit(
            actor_id=actor_id,
            action=AuditAction.DELETED.value,
            entity_type="attachments",
            entity_id=document["_id"],
            description=f"Removed attachment {presented['file_name']}.",
            before={"file_name": presented["file_name"], "entity_type": presented["entity_type"]},
        )
