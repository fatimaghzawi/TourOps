# TourOps ERD

Open this file and turn on **Markdown preview** (`Ctrl+Shift+V`).

Catalog spine: **supplier → supplier_services → package / tour snapshot**. A service cannot exist without a supplier.

```mermaid
erDiagram
  suppliers ||--o{ supplier_services : "supplier_id"
  supplier_services ||--o{ packages : "services[].supplier_service_id"
  supplier_services ||--o{ tours : "services[].supplier_service_id"
  packages |o--o{ tours : "package_id"
  suppliers ||--o{ supplier_reservations : "supplier_id"
  tours ||--o{ supplier_reservations : "tour_id"

  suppliers {
    ObjectId _id PK
    string supplier_number UK
    string name
    string supplier_type
    string preferred_payment_method
    object bank_details
    object hotel_info
    object transportation_info
    object tour_guide_info
    string status
  }

  supplier_services {
    ObjectId _id PK
    string service_number UK
    ObjectId supplier_id FK "required"
    string name
    string name_key
    string service_kind
    Decimal128 estimated_cost
    string cost_basis
    string status
  }

  packages {
    ObjectId _id PK
    string package_code UK
    string name
    int duration_days
    Decimal128 selling_price_per_person
    Decimal128 target_margin_percent
    array services "snapshot of catalog lines"
  }

  tours {
    ObjectId _id PK
    string tour_code UK
    ObjectId package_id FK "optional"
    datetime start_date
    datetime end_date
    int capacity
    int booked_seats
    int held_seats
    array services "copied from package or override"
    string status
  }

  supplier_reservations {
    ObjectId _id PK
    string reservation_number UK
    ObjectId tour_id FK
    ObjectId supplier_id FK
    string service_type
    string status
    string confirmation_number
  }
```

```mermaid
erDiagram
  customers ||--o{ bookings : "customer_id"
  tours ||--o{ bookings : "tour_id"
  bookings ||--o{ invoices : "booking_id"
  invoices ||--o{ payments : "invoice_id"
  payments ||--|| receipts : "payment_id"
  payments ||--o{ refunds : "payment_id"
  taxes |o--o{ invoices : "tax.tax_id"

  customers {
    ObjectId _id PK
    string customer_number UK
    string email UK
    string first_name
    string last_name
    object passport
  }

  bookings {
    ObjectId _id PK
    string booking_number UK
    ObjectId customer_id FK
    ObjectId tour_id FK
    array travelers
    object pricing
    string booking_status
    string payment_status
  }

  invoices {
    ObjectId _id PK
    string invoice_number UK
    ObjectId booking_id FK
    ObjectId customer_id "DN via booking"
    Decimal128 total_amount
    Decimal128 paid_amount
    Decimal128 refunded_amount
    Decimal128 remaining_amount "max(total-paid,0)"
    string status
  }

  payments {
    ObjectId _id PK
    string payment_number UK
    ObjectId invoice_id FK
    Decimal128 amount
    string status
  }

  receipts {
    ObjectId _id PK
    string receipt_number UK
    ObjectId payment_id FK
  }

  refunds {
    ObjectId _id PK
    string refund_number UK
    ObjectId payment_id FK
    Decimal128 amount
    string policy_tier
    string status
  }

  taxes {
    ObjectId _id PK
    string name
    Decimal128 rate
    string status
  }
```

```mermaid
erDiagram
  suppliers |o--o{ expenses : "supplier_id"
  tours |o--o{ expenses : "tour_id"
  expenses ||--o{ supplier_payments : "expense_id"

  expenses {
    ObjectId _id PK
    string expense_number UK
    string expense_scope "TOUR or GENERAL"
    string category
    ObjectId supplier_id FK "optional"
    ObjectId tour_id FK "required if TOUR"
    Decimal128 amount
    Decimal128 remaining_amount
    string payment_status
  }

  supplier_payments {
    ObjectId _id PK
    string supplier_payment_number UK
    ObjectId expense_id FK
    ObjectId supplier_id "DN via expense"
    Decimal128 amount
  }
```

Finance / reports are **not collections**. Profit is invoice revenue (`total − refunded`) minus expense documents. AR remaining is `max(total − paid, 0)` — refunds do not reopen the receivable.
