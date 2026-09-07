from enum import StrEnum


class Collections:
    USERS = "users"
    CUSTOMERS = "customers"
    SUPPLIERS = "suppliers"
    TOURS = "tours"
    PACKAGES = "packages"
    BOOKINGS = "bookings"
    INVOICES = "invoices"
    PAYMENTS = "payments"
    RECEIPTS = "receipts"
    REFUNDS = "refunds"
    EXPENSES = "expenses"
    SUPPLIER_PAYMENTS = "supplier_payments"
    AUDIT_LOGS = "audit_logs"
    NOTIFICATIONS = "notifications"
    SYSTEM_SETTINGS = "system_settings"
    TAXES = "taxes"
    ATTACHMENTS = "attachments"
    SUPPLIER_RESERVATIONS = "supplier_reservations"
    SUPPLIER_SERVICES = "supplier_services"

    COUNTERS = "counters"


class UserRole(StrEnum):
    TRAVEL_AGENT = "TRAVEL_AGENT"
    ACCOUNTANT = "ACCOUNTANT"
    OWNER_ADMIN = "OWNER_ADMIN"


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class RecordStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class SupplierType(StrEnum):
    HOTEL = "HOTEL"
    TRANSPORTATION = "TRANSPORTATION"
    TOUR_GUIDE = "TOUR_GUIDE"
    AIRLINE = "AIRLINE"
    ACTIVITY_PROVIDER = "ACTIVITY_PROVIDER"
    RESTAURANT = "RESTAURANT"
    INSURANCE = "INSURANCE"
    OTHER = "OTHER"


class SupplierServiceKind(StrEnum):
    ACCOMMODATION = "ACCOMMODATION"
    TRANSFER = "TRANSFER"
    TRANSPORTATION = "TRANSPORTATION"
    GUIDE = "GUIDE"
    ACTIVITY = "ACTIVITY"
    MEAL = "MEAL"
    OTHER = "OTHER"


class CostBasis(StrEnum):
    PER_PERSON = "PER_PERSON"
    PER_GROUP = "PER_GROUP"


class SupplierReservationStatus(StrEnum):
    REQUESTED = "REQUESTED"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class RoomType(StrEnum):
    SINGLE = "SINGLE"
    TWIN = "TWIN"
    DOUBLE = "DOUBLE"
    TRIPLE = "TRIPLE"
    QUAD = "QUAD"


class TourStatus(StrEnum):
    DRAFT = "DRAFT"
    AVAILABLE = "AVAILABLE"
    FULLY_BOOKED = "FULLY_BOOKED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class PackageStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class BookingStatus(StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class PaymentStatus(StrEnum):
    UNPAID = "UNPAID"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    REFUNDED = "REFUNDED"


class InvoiceStatus(StrEnum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    REFUNDED = "REFUNDED"
    CANCELLED = "CANCELLED"


class PaymentMethod(StrEnum):
    CASH = "CASH"
    BANK_TRANSFER = "BANK_TRANSFER"
    CARD = "CARD"
    CHEQUE = "CHEQUE"
    ONLINE = "ONLINE"
    OTHER = "OTHER"


class PaymentRecordStatus(StrEnum):
    COMPLETED = "COMPLETED"
    VOIDED = "VOIDED"


class DiscountType(StrEnum):
    FIXED = "FIXED"
    PERCENTAGE = "PERCENTAGE"
    NONE = "NONE"


class RefundStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"


class ExpenseScope(StrEnum):
    TOUR = "TOUR"
    GENERAL = "GENERAL"


class ExpenseCategory(StrEnum):
    HOTEL = "HOTEL"
    TRANSPORTATION = "TRANSPORTATION"
    TOUR_GUIDE = "TOUR_GUIDE"
    ACTIVITY = "ACTIVITY"
    FLIGHT = "FLIGHT"
    MEALS = "MEALS"
    INSURANCE = "INSURANCE"
    MARKETING = "MARKETING"
    RENT = "RENT"
    SALARY = "SALARY"
    UTILITIES = "UTILITIES"
    SOFTWARE = "SOFTWARE"
    OFFICE = "OFFICE"
    OTHER = "OTHER"


class ExpensePaymentStatus(StrEnum):
    UNPAID = "UNPAID"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"


class TaxStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class RefundPolicyTier(StrEnum):
    DAYS_30_PLUS = "30_PLUS"
    DAYS_15_TO_29 = "15_TO_29"
    DAYS_7_TO_14 = "7_TO_14"
    UNDER_7 = "UNDER_7"
    AGENCY_CANCEL = "AGENCY_CANCEL"
    OTHER = "OTHER"


class AttachmentCategory(StrEnum):
    PASSPORT = "PASSPORT"
    CONTRACT = "CONTRACT"
    RECEIPT = "RECEIPT"
    BOOKING_DOCUMENT = "BOOKING_DOCUMENT"
    GALLERY = "GALLERY"
    OTHER = "OTHER"


class AttachmentEntityType(StrEnum):
    CUSTOMERS = "customers"
    SUPPLIERS = "suppliers"
    EXPENSES = "expenses"
    BOOKINGS = "bookings"
    INVOICES = "invoices"
    PACKAGES = "packages"
    TOURS = "tours"


NUMBER_PREFIXES = {
    Collections.CUSTOMERS: "CUS",
    Collections.SUPPLIERS: "SUP",
    Collections.TOURS: "TOUR",
    Collections.PACKAGES: "PKG",
    Collections.BOOKINGS: "BK",
    Collections.INVOICES: "INV",
    Collections.PAYMENTS: "PAY",
    Collections.RECEIPTS: "REC",
    Collections.REFUNDS: "REF",
    Collections.EXPENSES: "EXP",
    Collections.SUPPLIER_PAYMENTS: "SP",
    Collections.SUPPLIER_RESERVATIONS: "SR",
    Collections.SUPPLIER_SERVICES: "SVC",
}

NUMBER_START = 1001  

DEFAULT_CURRENCY = "USD"
DEFAULT_TAX_NAME = "VAT"
