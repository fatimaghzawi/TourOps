from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from bson import ObjectId

from core.constants import SupplierReservationStatus, SupplierType


@dataclass
class SupplierReservationDocument:
    reservation_number: str
    tour_id: ObjectId
    supplier_id: ObjectId
    service_type: str
    start_date: datetime
    end_date: datetime
    recorded_by: ObjectId
    created_at: datetime
    updated_at: datetime
    status: str = SupplierReservationStatus.REQUESTED.value
    confirmation_number: Optional[str] = None
    release_date: Optional[datetime] = None
    quantity: Optional[int] = None
    notes: Optional[str] = None
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[ObjectId] = None
    _id: Optional[ObjectId] = None

    ALLOWED_STATUSES = {item.value for item in SupplierReservationStatus}
    ALLOWED_TYPES = {item.value for item in SupplierType}
