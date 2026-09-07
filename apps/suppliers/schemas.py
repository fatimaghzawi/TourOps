from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from bson import ObjectId

from core.constants import RecordStatus, SupplierType
from core.schemas import (
    ActivityProviderInfo,
    Address,
    AirlineInfo,
    BankDetails,
    HotelInfo,
    InsuranceInfo,
    OtherSupplierInfo,
    RestaurantInfo,
    TourGuideInfo,
    TransportationInfo,
)


@dataclass
class SupplierDocument:
    supplier_number: str
    name: str
    supplier_type: str
    created_by: ObjectId
    created_at: datetime
    updated_at: datetime
    contact_person: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Address = field(default_factory=Address)
    tax_number: Optional[str] = None
    payment_terms: Optional[str] = None
    preferred_payment_method: Optional[str] = None
    bank_details: BankDetails = field(default_factory=BankDetails)
    hotel_info: Optional[HotelInfo] = None
    transportation_info: Optional[TransportationInfo] = None
    tour_guide_info: Optional[TourGuideInfo] = None
    airline_info: Optional[AirlineInfo] = None
    activity_info: Optional[ActivityProviderInfo] = None
    restaurant_info: Optional[RestaurantInfo] = None
    insurance_info: Optional[InsuranceInfo] = None
    other_info: Optional[OtherSupplierInfo] = None
    notes: Optional[str] = None
    status: str = RecordStatus.ACTIVE.value
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[ObjectId] = None
    _id: Optional[ObjectId] = None

    ALLOWED_TYPES = {item.value for item in SupplierType}

    TYPE_INFO_FIELD = {
        SupplierType.HOTEL.value: "hotel_info",
        SupplierType.TRANSPORTATION.value: "transportation_info",
        SupplierType.TOUR_GUIDE.value: "tour_guide_info",
        SupplierType.AIRLINE.value: "airline_info",
        SupplierType.ACTIVITY_PROVIDER.value: "activity_info",
        SupplierType.RESTAURANT.value: "restaurant_info",
        SupplierType.INSURANCE.value: "insurance_info",
        SupplierType.OTHER.value: "other_info",
    }


SUPPLIER_HOTEL_EXAMPLE = {
    "_id": "ObjectId",
    "supplier_number": "SUP-1001",
    "name": "Nile View Hotel",
    "supplier_type": "HOTEL",
    "contact_person": "Sara Ali",
    "email": "reservations@nileview.example",
    "phone": "+20 2 555 0100",
    "address": {"country": "Egypt", "city": "Cairo", "street": "Corniche El Nile"},
    "tax_number": "TAX-7788",
    "payment_terms": "Net 14",
    "preferred_payment_method": "BANK_TRANSFER",
    "bank_details": {
        "bank_name": "Banque Misr",
        "account_name": "Nile View Hotel",
        "iban": "EG...",
        "swift_bic": "BMISEGCX",
        "account_number": None,
    },
    "hotel_info": {
        "star_rating": 4,
    },
    "transportation_info": None,
    "tour_guide_info": None,
    "airline_info": None,
    "activity_info": None,
    "restaurant_info": None,
    "insurance_info": None,
    "other_info": None,
    "notes": None,
    "status": "ACTIVE",
    "is_deleted": False,
    "deleted_at": None,
    "deleted_by": None,
    "created_at": "datetime",
    "updated_at": "datetime",
}
