from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

from bson import ObjectId

from core.constants import InvoiceStatus
from core.money import ZERO
from core.schemas import Discount, InvoiceLineItem, Tax


@dataclass
class InvoiceDocument:
    invoice_number: str
    booking_id: ObjectId
    customer_id: ObjectId
    issue_date: datetime
    due_date: datetime
    created_by: ObjectId
    created_at: datetime
    updated_at: datetime
    line_items: list[InvoiceLineItem] = field(default_factory=list)
    subtotal: Decimal = ZERO
    discount: Discount = field(default_factory=Discount)
    taxable_amount: Decimal = ZERO
    tax: Tax = field(default_factory=Tax)
    total_amount: Decimal = ZERO
    paid_amount: Decimal = ZERO
    refunded_amount: Decimal = ZERO
    remaining_amount: Decimal = ZERO
    status: str = InvoiceStatus.DRAFT.value
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[ObjectId] = None
    _id: Optional[ObjectId] = None
