from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

from bson import ObjectId

from core.constants import BookingStatus, DiscountType, PaymentStatus
from core.money import ZERO
from core.schemas import Traveler


@dataclass
class BookingPricing:
    unit_price: Decimal = ZERO
    subtotal: Decimal = ZERO
    discount_type: str = DiscountType.NONE.value
    discount_value: Decimal = ZERO
    discount_amount: Decimal = ZERO
    discount_reason: Optional[str] = None
    discount_applied_by: Optional[ObjectId] = None
    taxable_amount: Decimal = ZERO
    tax_id: Optional[ObjectId] = None
    tax_rate: Decimal = ZERO
    tax_amount: Decimal = ZERO
    total_amount: Decimal = ZERO


@dataclass
class BookingDocument:
    booking_number: str
    customer_id: ObjectId
    tour_id: ObjectId
    travelers_count: int
    booking_date: datetime
    created_by: ObjectId
    created_at: datetime
    updated_at: datetime
    updated_by: ObjectId
    travelers: list[Traveler] = field(default_factory=list)
    pricing: BookingPricing = field(default_factory=BookingPricing)
    booking_status: str = BookingStatus.PENDING.value
    payment_status: str = PaymentStatus.UNPAID.value
    notes: Optional[str] = None
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[ObjectId] = None
    _id: Optional[ObjectId] = None
