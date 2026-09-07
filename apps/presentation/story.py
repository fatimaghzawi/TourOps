from __future__ import annotations

from apps.presentation.constants import STORY
from core.constants import (
    Collections,
    InvoiceStatus,
    PaymentRecordStatus,
    SupplierReservationStatus,
    SupplierType,
)
from core.database import get_collection
from core.exceptions import DatabaseUnavailableError
from core.utils import parse_object_id, serialize_id


def _id(document) -> str:
    if not document:
        return ""
    return serialize_id(document.get("_id") or document.get("id"))


def find_story() -> dict | None:
    try:
        suppliers = get_collection(Collections.SUPPLIERS)
        packages = get_collection(Collections.PACKAGES)
        tours = get_collection(Collections.TOURS)
        reservations = get_collection(Collections.SUPPLIER_RESERVATIONS)
        expenses = get_collection(Collections.EXPENSES)
    except Exception as extra:
        raise DatabaseUnavailableError("Could not load the Istanbul Escape story.") from extra

    hotel = suppliers.find_one({"name": STORY["hotel"], "is_deleted": {"$ne": True}})
    transport = suppliers.find_one({"name": STORY["transport"], "is_deleted": {"$ne": True}})
    guide = suppliers.find_one({"name": STORY["guide"], "is_deleted": {"$ne": True}})
    package = packages.find_one({"name": STORY["package_name"], "is_deleted": {"$ne": True}})
    tour = tours.find_one({"name": STORY["tour_name"], "is_deleted": {"$ne": True}})
    if not all([hotel, transport, guide, package, tour]):
        return None

    def reservation_for(supplier):
        return reservations.find_one(
            {
                "tour_id": tour["_id"],
                "supplier_id": supplier["_id"],
                "is_deleted": {"$ne": True},
            }
        )

    hotel_res = reservation_for(hotel)
    transport_res = reservation_for(transport)
    guide_res = reservation_for(guide)
    hotel_expense = expenses.find_one(
        {
            "tour_id": tour["_id"],
            "supplier_id": hotel["_id"],
            "is_deleted": {"$ne": True},
        }
    )
    return {
        "tour_id": _id(tour),
        "package_id": _id(package),
        "hotel_id": _id(hotel),
        "transport_id": _id(transport),
        "guide_id": _id(guide),
        "hotel_res_id": _id(hotel_res),
        "transport_res_id": _id(transport_res),
        "guide_res_id": _id(guide_res),
        "hotel_expense_id": _id(hotel_expense),
        "tour_name": tour.get("name") or STORY["tour_name"],
        "capacity": int(tour.get("capacity") or STORY["capacity"]),
        "hotel_type": hotel.get("supplier_type") or SupplierType.HOTEL.value,
    }


def live_state(story: dict) -> dict:
    tour_id = (story or {}).get("tour_id")
    if not tour_id:
        return {}
    try:
        oid = parse_object_id(tour_id, field="tour_id")
        tour = get_collection(Collections.TOURS).find_one({"_id": oid, "is_deleted": {"$ne": True}})
        if not tour:
            return {}
        rows = list(
            get_collection(Collections.SUPPLIER_RESERVATIONS).find(
                {"tour_id": tour["_id"], "is_deleted": {"$ne": True}}
            )
        )
    except Exception:
        return {}
    live = [row for row in rows if row.get("status") != SupplierReservationStatus.CANCELLED.value]
    confirmed = sum(1 for row in live if row.get("status") == SupplierReservationStatus.CONFIRMED.value)
    booked = int(tour.get("booked_seats") or 0)
    held = int(tour.get("held_seats") or 0)
    capacity = int(tour.get("capacity") or 0)
    available = max(capacity - booked - held, 0)
    ready = bool(live) and confirmed == len(live)
    return {
        "booked": booked,
        "capacity": capacity,
        "available": available,
        "confirmed": confirmed,
        "planned": len(live),
        "can_take_bookings": ready,
        "block_reason": ""
        if ready
        else "This tour cannot take client bookings until every planned supplier has confirmed.",
    }


def demo_cast(story: dict | None = None) -> dict:
    cast = {
        "tour_id": (story or {}).get("tour_id") or "",
        "hotel_res_id": (story or {}).get("hotel_res_id") or "",
        "guide_res_id": (story or {}).get("guide_res_id") or "",
        "transport_res_id": (story or {}).get("transport_res_id") or "",
        "hotel_expense_id": (story or {}).get("hotel_expense_id") or "",
        "customer_id": "",
        "invoice_id": "",
        "payment_id": "",
        **{key: STORY[key] for key in STORY},
    }
    try:
        maya = get_collection(Collections.CUSTOMERS).find_one(
            {"email": STORY["maya_email"], "is_deleted": {"$ne": True}}
        )
        cast["customer_id"] = _id(maya)
        open_invoice = get_collection(Collections.INVOICES).find_one(
            {
                "status": {"$in": [InvoiceStatus.ISSUED.value, InvoiceStatus.PARTIALLY_PAID.value]},
                "is_deleted": {"$ne": True},
            }
        )
        if not open_invoice:
            open_invoice = get_collection(Collections.INVOICES).find_one({"is_deleted": {"$ne": True}})
        cast["invoice_id"] = _id(open_invoice)
        payment = get_collection(Collections.PAYMENTS).find_one(
            {"status": PaymentRecordStatus.COMPLETED.value, "is_deleted": {"$ne": True}}
        )
        cast["payment_id"] = _id(payment)
    except Exception:
        pass
    return cast
