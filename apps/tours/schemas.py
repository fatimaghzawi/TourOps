from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

from bson import ObjectId

from core.constants import TourStatus
from core.schemas import Destination, SupplierServiceLine


def available_seats(
    capacity: int,
    booked_seats: int,
    held_seats: int = 0,
) -> int:
    return max(
        capacity - booked_seats - held_seats,
        0,
    )


@dataclass
class TourDocument:
    tour_code: str
    name: str
    destination: Destination
    description: str
    start_date: datetime
    end_date: datetime
    capacity: int
    booked_seats: int
    selling_price_per_person: Decimal
    currency: str
    created_by: ObjectId
    created_at: datetime
    updated_at: datetime
    held_seats: int = 0
    package_id: Optional[ObjectId] = None
    updated_by: Optional[ObjectId] = None
    status: str = TourStatus.DRAFT.value
    services: list[SupplierServiceLine] = field(default_factory=list)
    included_services: list[str] = field(default_factory=list)
    excluded_services: list[str] = field(default_factory=list)
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[ObjectId] = None
    _id: Optional[ObjectId] = None

    @property
    def available_seats(self) -> int:
     return max(
        self.capacity - self.booked_seats - self.held_seats,
        0,
    )
