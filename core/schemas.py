from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

from bson import ObjectId

from core.money import ZERO


@dataclass
class Address:
    country: str = ""
    city: str = ""
    street: Optional[str] = None


@dataclass
class Passport:
    number: Optional[str] = None
    expiry_date: Optional[datetime] = None
    issuing_country: Optional[str] = None


@dataclass
class EmergencyContact:
    name: Optional[str] = None
    phone: Optional[str] = None
    relationship: Optional[str] = None


@dataclass
class BankDetails:
    bank_name: Optional[str] = None
    account_name: Optional[str] = None
    iban: Optional[str] = None
    swift_bic: Optional[str] = None
    account_number: Optional[str] = None


@dataclass
class HotelInfo:
    star_rating: Optional[int] = None


@dataclass
class TransportationInfo:
    vehicle_type: Optional[str] = None
    fleet_size: Optional[int] = None
    seats_per_vehicle: Optional[int] = None
    license_number: Optional[str] = None
    coverage_areas: list[str] = field(default_factory=list)


@dataclass
class TourGuideInfo:
    languages: list[str] = field(default_factory=list)
    license_number: Optional[str] = None
    specialties: list[str] = field(default_factory=list)
    years_experience: Optional[int] = None


@dataclass
class AirlineInfo:
    iata_code: Optional[str] = None
    alliance: Optional[str] = None


@dataclass
class ActivityProviderInfo:
    activity_kinds: list[str] = field(default_factory=list)
    typical_duration_hours: Optional[int] = None
    location: Optional[str] = None


@dataclass
class RestaurantInfo:
    cuisine: Optional[str] = None
    seating_capacity: Optional[int] = None
    meal_types: list[str] = field(default_factory=list)


@dataclass
class InsuranceInfo:
    policy_types: list[str] = field(default_factory=list)
    coverage_notes: Optional[str] = None


@dataclass
class OtherSupplierInfo:
    details: Optional[str] = None


@dataclass
class Destination:
    country: str = ""
    city: str = ""


@dataclass
class SupplierServiceLine:
    supplier_id: ObjectId
    supplier_type: str
    description: str
    estimated_cost: Decimal = ZERO
    supplier_service_id: Optional[ObjectId] = None
    name: Optional[str] = None


@dataclass
class Traveler:
    first_name: str = ""
    last_name: str = ""
    passport_number: Optional[str] = None
    nationality: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    room_type: Optional[str] = None
    room_number: Optional[str] = None
    hotel_reservation_id: Optional[ObjectId] = None


@dataclass
class InvoiceLineItem:
    description: str = ""
    quantity: int = 1
    unit_price: Decimal = ZERO
    total: Decimal = ZERO


@dataclass
class Discount:
    type: str = "NONE"
    value: Decimal = ZERO
    amount: Decimal = ZERO
    reason: Optional[str] = None
    applied_by: Optional[ObjectId] = None


@dataclass
class Tax:
    name: str = "VAT"
    rate: Decimal = ZERO
    amount: Decimal = ZERO
    tax_id: Optional[ObjectId] = None


@dataclass
class RelatedEntity:
    type: str = ""
    id: ObjectId = field(default_factory=ObjectId)


@dataclass
class AgencyInfo:
    name: str = "TourOps"
    email: str = ""
    phone: str = ""
    address: str = ""
