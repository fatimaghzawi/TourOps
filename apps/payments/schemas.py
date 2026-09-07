from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from bson import ObjectId

from core.constants import PaymentMethod, PaymentRecordStatus
from core.money import ZERO


@dataclass
class PaymentDocument:
    payment_number: str
    invoice_id: ObjectId
    booking_id: ObjectId
    customer_id: ObjectId
    amount: Decimal
    currency: str
    payment_method: str
    payment_date: datetime
    recorded_by: ObjectId
    created_at: datetime
    reference_number: Optional[str] = None
    status: str = PaymentRecordStatus.COMPLETED.value
    notes: Optional[str] = None
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[ObjectId] = None
    _id: Optional[ObjectId] = None
