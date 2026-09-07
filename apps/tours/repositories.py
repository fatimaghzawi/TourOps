from __future__ import annotations

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.collection import Collection

from apps.expenses.constants import MONEY_FIELDS as EXPENSE_MONEY
from apps.tours.constants import MONEY_FIELDS
from core.constants import BookingStatus, Collections
from core.database import get_collection
from core.money import ZERO, money_dict, to_money
from core.soft_delete import LIVE_FILTER, SoftDeleteRepositoryMixin, live_query
from core.utils import parse_object_id


class TourRepository(SoftDeleteRepositoryMixin):
    def __init__(
        self,
        collection: Collection | None = None,
        *,
        packages: Collection | None = None,
        suppliers: Collection | None = None,
        bookings: Collection | None = None,
        expenses: Collection | None = None,
        customers: Collection | None = None,
    ):
        self.collection = collection or get_collection(Collections.TOURS)
        self.packages = packages if packages is not None else get_collection(Collections.PACKAGES)
        self.suppliers = suppliers if suppliers is not None else get_collection(Collections.SUPPLIERS)
        self.bookings = bookings if bookings is not None else get_collection(Collections.BOOKINGS)
        self.expenses = expenses if expenses is not None else get_collection(Collections.EXPENSES)
        self.customers = customers if customers is not None else get_collection(Collections.CUSTOMERS)

    def find_by_id(self, doc_id: str | ObjectId, *, include_deleted: bool = False) -> dict | None:
        query = {"_id": parse_object_id(doc_id, field="tour_id")}
        if not include_deleted:
            query.update(LIVE_FILTER)
        document = self.collection.find_one(query)
        return money_dict(document, *MONEY_FIELDS) if document else None

    def list_tours(self, extra: dict | None = None) -> list[dict]:
        return [
            money_dict(document, *MONEY_FIELDS)
            for document in self.collection.find(live_query(extra)).sort("start_date", 1)
        ]

    def find_package(self, package_id: str | ObjectId) -> dict | None:
        query = live_query({"_id": parse_object_id(package_id, field="package_id")})
        document = self.packages.find_one(query)
        return money_dict(document, "selling_price_per_person") if document else None

    def find_supplier(self, supplier_id: str | ObjectId) -> dict | None:
        query = live_query({"_id": parse_object_id(supplier_id, field="supplier_id")})
        return self.suppliers.find_one(query)

    def list_suppliers(self) -> list[dict]:
        return list(self.suppliers.find(live_query()).sort("name", 1))

    def find_customer(self, customer_id: str | ObjectId) -> dict | None:
        query = live_query({"_id": parse_object_id(customer_id, field="customer_id")})
        return self.customers.find_one(query)

    def list_bookings_for(self, tour_id: str | ObjectId) -> list[dict]:
        query = live_query({"tour_id": parse_object_id(tour_id, field="tour_id")})
        return list(self.bookings.find(query).sort("booking_date", -1))

    def list_expenses_for(self, tour_id: str | ObjectId) -> list[dict]:
        query = live_query({"tour_id": parse_object_id(tour_id, field="tour_id")})
        return [
            money_dict(document, *EXPENSE_MONEY)
            for document in self.expenses.find(query).sort("expense_date", -1)
        ]

    def costs_by_tour(self) -> dict[str, object]:
        totals: dict[str, object] = {}
        for document in self.expenses.find(live_query()):
            hydrated = money_dict(document, *EXPENSE_MONEY)
            tour_id = hydrated.get("tour_id")
            if not tour_id:
                continue
            key = str(tour_id)
            totals[key] = to_money(totals.get(key, ZERO)) + to_money(hydrated.get("amount"))
        return totals

    def has_live_bookings(self, tour_id: str | ObjectId) -> bool:
        oid = parse_object_id(tour_id, field="tour_id")
        for document in self.bookings.find(live_query({"tour_id": oid})):
            if document.get("booking_status") != BookingStatus.CANCELLED.value:
                return True
        return False

    def try_increment_booked_seats(self, tour_id: str | ObjectId, seats: int, *, max_booked: int) -> dict | None:
        """Atomically consume seats if booked_seats is still within capacity."""
        return self.collection.find_one_and_update(
            live_query({
                "_id": parse_object_id(tour_id, field="tour_id"),
                "booked_seats": {"$lte": max_booked},
            }),
            {"$inc": {"booked_seats": seats}},
            return_document=ReturnDocument.AFTER,
        )

    def try_decrement_booked_seats(self, tour_id: str | ObjectId, seats: int) -> dict | None:
        """Atomically restore seats without going below zero."""
        return self.collection.find_one_and_update(
            live_query({
                "_id": parse_object_id(tour_id, field="tour_id"),
                "booked_seats": {"$gte": seats},
            }),
            {"$inc": {"booked_seats": -seats}},
            return_document=ReturnDocument.AFTER,
        )

    def hold_seats(self, tour_id: str | ObjectId, seats: int) -> bool:
        oid = parse_object_id(tour_id, field="tour_id")

        result = self.collection.update_one(
            {
                "_id": oid,
                **LIVE_FILTER,
                "status": "AVAILABLE",
                "$expr": {
                    "$gte": [
                        {
                            "$subtract": [
                                "$capacity",
                                {
                                    "$add": [
                                        "$booked_seats",
                                        {"$ifNull": ["$held_seats", 0]},
                                    ]
                                },
                            ]
                        },
                        seats,
                    ]
                },
            },
            {
                "$inc": {
                    "held_seats": seats,
                }
            },
        )

        return result.modified_count == 1



    def confirm_seats(self, tour_id: str | ObjectId, seats: int) -> bool:
        oid = parse_object_id(tour_id, field="tour_id")

        result = self.collection.update_one(
            {
                "_id": oid,
                **LIVE_FILTER,
                "$expr": {
                    "$gte": [
                        {"$ifNull": ["$held_seats", 0]},
                        seats,
                    ]
                },
            },
            {
                "$inc": {
                    "held_seats": -seats,
                    "booked_seats": seats,
                }
            },
        )

        return result.modified_count == 1


    def restore_held_seats(
        self,
        tour_id: str | ObjectId,
        seats: int,
    ) -> bool:
        oid = parse_object_id(tour_id, field="tour_id")

        result = self.collection.update_one(
            {
                "_id": oid,
                **LIVE_FILTER,
            },
            {
                "$inc": {
                    "held_seats": seats,
                    "booked_seats": -seats,
                }
            },
        )

        return result.modified_count == 1

    def release_seats(self, tour_id: str | ObjectId, seats: int) -> bool:
     oid = parse_object_id(tour_id, field="tour_id")

     result = self.collection.update_one(
        {
            "_id": oid,
            **LIVE_FILTER,
            "$expr": {
                "$gte": [
                    {"$ifNull": ["$held_seats", 0]},
                    seats,
                ]
            },
        },
        {
            "$inc": {
                "held_seats": -seats,
            }
        },
    )

     return result.modified_count == 1
