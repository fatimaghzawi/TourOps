from __future__ import annotations

from pymongo.collection import Collection

from core.constants import Collections
from core.database import get_collection
from core.soft_delete import live_query
from core.utils import parse_object_id


class ReportRepository:
    def __init__(
        self,
        *,
        expenses: Collection | None = None,
        supplier_payments: Collection | None = None,
        invoices: Collection | None = None,
        payments: Collection | None = None,
        refunds: Collection | None = None,
        bookings: Collection | None = None,
        tours: Collection | None = None,
        customers: Collection | None = None,
        suppliers: Collection | None = None,
    ):
        self.expenses = expenses if expenses is not None else get_collection(Collections.EXPENSES)
        self.supplier_payments = (
            supplier_payments if supplier_payments is not None else get_collection(Collections.SUPPLIER_PAYMENTS)
        )
        self.invoices = invoices if invoices is not None else get_collection(Collections.INVOICES)
        self.payments = payments if payments is not None else get_collection(Collections.PAYMENTS)
        self.refunds = refunds if refunds is not None else get_collection(Collections.REFUNDS)
        self.bookings = bookings if bookings is not None else get_collection(Collections.BOOKINGS)
        self.tours = tours if tours is not None else get_collection(Collections.TOURS)
        self.customers = customers if customers is not None else get_collection(Collections.CUSTOMERS)
        self.suppliers = suppliers if suppliers is not None else get_collection(Collections.SUPPLIERS)

    def live(self, collection: Collection) -> list[dict]:
        return list(collection.find(live_query()))

    def find(self, collection, doc_id) -> dict | None:
        return collection.find_one(live_query({"_id": parse_object_id(doc_id)}))
