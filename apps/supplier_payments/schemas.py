from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from bson import ObjectId

from core.constants import PaymentMethod


@dataclass
class SupplierPaymentDocument:
    supplier_payment_number: str
    supplier_id: ObjectId
    expense_id: ObjectId
    amount: Decimal
    currency: str
    payment_method: str
    payment_date: datetime
    recorded_by: ObjectId
    created_at: datetime
    reference_number: Optional[str] = None
    notes: Optional[str] = None
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[ObjectId] = None
    _id: Optional[ObjectId] = None

    ALLOWED_METHODS = {item.value for item in PaymentMethod}


SUPPLIER_PAYMENT_DOCUMENT_EXAMPLE = {
    "_id": "ObjectId",
    "supplier_payment_number": "SP-1001",
    "supplier_id": "ObjectId",
    "expense_id": "ObjectId",
    "amount": "1000.00",
    "currency": "USD",
    "payment_method": "BANK_TRANSFER",
    "payment_date": "datetime",
    "reference_number": "AP-4410",
    "notes": None,
    "recorded_by": "ObjectId",
    "is_deleted": False,
    "deleted_at": None,
    "deleted_by": None,
    "created_at": "datetime",
}
