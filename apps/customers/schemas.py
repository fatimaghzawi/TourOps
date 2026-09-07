from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from bson import ObjectId

from core.constants import RecordStatus
from core.schemas import Address, EmergencyContact, Passport


@dataclass
class CustomerDocument:
    customer_number: str
    first_name: str
    last_name: str
    email: str
    phone: str
    created_by: ObjectId
    created_at: datetime
    updated_at: datetime
    date_of_birth: Optional[datetime] = None
    nationality: Optional[str] = None
    address: Address = field(default_factory=Address)
    passport: Passport = field(default_factory=Passport)
    emergency_contact: EmergencyContact = field(default_factory=EmergencyContact)
    notes: Optional[str] = None
    status: str = RecordStatus.ACTIVE.value
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[ObjectId] = None
    _id: Optional[ObjectId] = None
