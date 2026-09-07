from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

from bson import ObjectId

from core.constants import DEFAULT_CURRENCY, DEFAULT_TAX_NAME
from core.money import ZERO
from core.schemas import AgencyInfo


@dataclass
class TaxSettings:
    name: str = DEFAULT_TAX_NAME
    default_rate: Decimal = ZERO
    enabled: bool = True


@dataclass
class PrefixedSeries:
    prefix: str
    default_due_days: Optional[int] = None


@dataclass
class SystemSettingsDocument:
    agency: AgencyInfo = field(default_factory=AgencyInfo)
    currency: str = DEFAULT_CURRENCY
    default_tax_id: Optional[ObjectId] = None
    tax: TaxSettings = field(default_factory=TaxSettings)
    invoice: dict = field(default_factory=lambda: {"prefix": "INV", "default_due_days": 14})
    booking: dict = field(default_factory=lambda: {"prefix": "BK"})
    payment: dict = field(default_factory=lambda: {"prefix": "PAY"})
    expense: dict = field(default_factory=lambda: {"prefix": "EXP"})
    updated_by: Optional[ObjectId] = None
    updated_at: Optional[datetime] = None
    _id: Optional[ObjectId] = None
