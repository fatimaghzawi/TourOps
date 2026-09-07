from core.constants import AttachmentCategory, AttachmentEntityType

CATEGORY_LABELS = {
    AttachmentCategory.PASSPORT.value: "Passport",
    AttachmentCategory.CONTRACT.value: "Contract",
    AttachmentCategory.RECEIPT.value: "Receipt",
    AttachmentCategory.BOOKING_DOCUMENT.value: "Booking document",
    AttachmentCategory.GALLERY.value: "Tour gallery",
    AttachmentCategory.OTHER.value: "Other",
}
CATEGORY_CHOICES = tuple(CATEGORY_LABELS.items())

ENTITY_LABELS = {
    AttachmentEntityType.CUSTOMERS.value: "Customer",
    AttachmentEntityType.SUPPLIERS.value: "Supplier",
    AttachmentEntityType.EXPENSES.value: "Expense",
    AttachmentEntityType.BOOKINGS.value: "Booking",
    AttachmentEntityType.INVOICES.value: "Invoice",
    AttachmentEntityType.PACKAGES.value: "Package",
    AttachmentEntityType.TOURS.value: "Tour",
}
ENTITY_CHOICES = tuple(ENTITY_LABELS.items())

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "text/plain",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_GALLERY_FILES = 8


def sniff_content_type(header: bytes) -> str | None:
    sample = header or b""
    if sample.startswith(b"%PDF"):
        return "application/pdf"
    if sample.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if sample.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if sample.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if sample.startswith(b"RIFF") and b"WEBP" in sample[:16]:
        return "image/webp"
    if sample.startswith(b"PK"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if sample.startswith(b"\xd0\xcf\x11\xe0"):
        return "application/msword"
    return None
