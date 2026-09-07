from core.constants import Collections
from core.database import get_collection


RECOMMENDED_INDEXES = [
    (Collections.USERS, [("email", 1)], True, {"partialFilterExpression": {"is_deleted": False}}),
    (Collections.CUSTOMERS, [("customer_number", 1)], True, None),
    (Collections.CUSTOMERS, [("email", 1)], True, {"partialFilterExpression": {"is_deleted": False}}),
    (Collections.SUPPLIERS, [("supplier_number", 1)], True, None),
    (Collections.SUPPLIERS, [("supplier_type", 1)], False, None),
    (Collections.SUPPLIER_SERVICES, [("service_number", 1)], True, None),
    (Collections.SUPPLIER_SERVICES, [("supplier_id", 1)], False, None),
    (
        Collections.SUPPLIER_SERVICES,
        [("supplier_id", 1), ("name_key", 1)],
        True,
        {"partialFilterExpression": {"is_deleted": False}},
    ),
    (Collections.TOURS, [("tour_code", 1)], True, None),
    (Collections.TOURS, [("package_id", 1)], False, None),
    (Collections.TOURS, [("start_date", 1)], False, None),
    (Collections.TOURS, [("status", 1)], False, None),
    (Collections.PACKAGES, [("package_code", 1)], True, None),
    (Collections.BOOKINGS, [("booking_number", 1)], True, None),
    (Collections.BOOKINGS, [("customer_id", 1)], False, None),
    (Collections.BOOKINGS, [("tour_id", 1)], False, None),
    (Collections.INVOICES, [("invoice_number", 1)], True, None),
    (
        Collections.INVOICES,
        [("booking_id", 1)],
        True,
        {"partialFilterExpression": {"is_deleted": False, "live_for_booking": True}},
    ),
    (Collections.PAYMENTS, [("payment_number", 1)], True, None),
    (Collections.PAYMENTS, [("invoice_id", 1)], False, None),
    (Collections.RECEIPTS, [("receipt_number", 1)], True, None),
    (Collections.REFUNDS, [("refund_number", 1)], True, None),
    (Collections.EXPENSES, [("expense_number", 1)], True, None),
    (Collections.EXPENSES, [("tour_id", 1)], False, None),
    (Collections.EXPENSES, [("supplier_id", 1)], False, None),
    (Collections.SUPPLIER_PAYMENTS, [("supplier_payment_number", 1)], True, None),
    (Collections.SUPPLIER_PAYMENTS, [("expense_id", 1)], False, None),
    (Collections.SUPPLIER_PAYMENTS, [("supplier_id", 1)], False, None),
    (Collections.SUPPLIER_RESERVATIONS, [("reservation_number", 1)], True, None),
    (Collections.SUPPLIER_RESERVATIONS, [("tour_id", 1)], False, None),
    (Collections.SUPPLIER_RESERVATIONS, [("supplier_id", 1)], False, None),
    (Collections.AUDIT_LOGS, [("entity_type", 1), ("entity_id", 1)], False, None),
    (Collections.NOTIFICATIONS, [("user_id", 1), ("is_read", 1)], False, None),
    (Collections.TAXES, [("name", 1), ("effective_from", 1)], False, None),
    (Collections.TAXES, [("status", 1), ("effective_from", 1)], False, None),
    (Collections.ATTACHMENTS, [("entity_type", 1), ("entity_id", 1)], False, None),
]


def _drop_replaced_indexes() -> None:
    invoices = get_collection(Collections.INVOICES)
    try:
        invoices.drop_index("booking_id_1")
    except Exception:
        pass


def ensure_indexes() -> list[str]:
    _drop_replaced_indexes()
    created = []
    for collection_name, keys, unique, extra in RECOMMENDED_INDEXES:
        options = {"unique": unique}
        if extra:
            options.update(extra)
        get_collection(collection_name).create_index(keys, **options)
        created.append(f"{collection_name}: {keys} {options}")
    return created


def ensure_indexes_quietly() -> None:
    import logging
    import sys

    from django.conf import settings

    if "pytest" in sys.modules:
        return
    try:
        ensure_indexes()
    except Exception:
        logging.getLogger(__name__).exception("Could not ensure MongoDB indexes.")
        if not getattr(settings, "DEBUG", True):
            raise
