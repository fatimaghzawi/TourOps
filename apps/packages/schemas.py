from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

from bson import ObjectId

from core.constants import PackageStatus
from core.schemas import Destination, SupplierServiceLine


@dataclass
class PackageDocument:
    package_code: str
    name: str
    description: str
    destination: Destination
    duration_days: int
    selling_price_per_person: Decimal
    currency: str
    default_capacity: int
    created_by: ObjectId
    created_at: datetime
    updated_at: datetime
    services: list[SupplierServiceLine] = field(default_factory=list)
    included_services: list[str] = field(default_factory=list)
    excluded_services: list[str] = field(default_factory=list)
    status: str = PackageStatus.ACTIVE.value
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[ObjectId] = None
    _id: Optional[ObjectId] = None
