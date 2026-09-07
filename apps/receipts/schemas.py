from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from bson import ObjectId


@dataclass
class ReceiptDocument:
    receipt_number: str
    payment_id: ObjectId
    invoice_id: ObjectId
    customer_id: ObjectId
    amount: Decimal
    payment_method: str
    issued_at: datetime
    issued_by: ObjectId
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[ObjectId] = None
    _id: Optional[ObjectId] = None
