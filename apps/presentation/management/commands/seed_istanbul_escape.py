"""Wipe business records and seed the Istanbul Escape presentation dataset."""

from __future__ import annotations

import shutil
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.accounts.settings_service import SettingsService
from apps.attachments.services import AttachmentService
from apps.bookings.services import BookingService
from apps.customers.services import CustomerService
from apps.expenses.services import ExpenseService
from apps.invoices.services import InvoiceService
from apps.packages.services import PackageService
from apps.payments.services import PaymentService
from apps.presentation.constants import STORY
from apps.supplier_reservations.services import SupplierReservationService
from apps.suppliers.offerings import SupplierOfferingService
from apps.suppliers.services import SupplierService
from apps.tours.services import TourService
from core.constants import (
    AttachmentCategory,
    AttachmentEntityType,
    Collections,
    CostBasis,
    ExpenseCategory,
    ExpenseScope,
    PaymentMethod,
    SupplierReservationStatus,
    SupplierServiceKind,
    SupplierType,
)
from core.database import get_collection
from core.exceptions import DatabaseUnavailableError
from core.indexes import ensure_indexes

WIPE = (
    Collections.CUSTOMERS,
    Collections.SUPPLIERS,
    Collections.SUPPLIER_SERVICES,
    Collections.PACKAGES,
    Collections.TOURS,
    Collections.BOOKINGS,
    Collections.INVOICES,
    Collections.PAYMENTS,
    Collections.RECEIPTS,
    Collections.REFUNDS,
    Collections.EXPENSES,
    Collections.SUPPLIER_PAYMENTS,
    Collections.SUPPLIER_RESERVATIONS,
    Collections.ATTACHMENTS,
    Collections.NOTIFICATIONS,
    Collections.AUDIT_LOGS,
    Collections.TAXES,
    Collections.COUNTERS,
    Collections.SYSTEM_SETTINGS,
)

# 11 households × 2 travelers = 22 seats paid. Maya adds 2 live.
HOUSEHOLDS = (
    {
        "first": "Ayla",
        "partner": "Can",
        "last": "Demir",
        "phone": "+90 532 441 1101",
        "city": "Kadikoy",
        "passport": "U4411101",
        "partner_passport": "U4411102",
        "room": "301",
    },
    {
        "first": "Emre",
        "partner": "Selin",
        "last": "Kaya",
        "phone": "+90 532 441 1103",
        "city": "Besiktas",
        "passport": "U4411103",
        "partner_passport": "U4411104",
        "room": "302",
    },
    {
        "first": "Deniz",
        "partner": "Elif",
        "last": "Yilmaz",
        "phone": "+90 532 441 1105",
        "city": "Sisli",
        "passport": "U4411105",
        "partner_passport": "U4411106",
        "room": "303",
    },
    {
        "first": "Burak",
        "partner": "Ece",
        "last": "Aydin",
        "phone": "+90 532 441 1107",
        "city": "Uskudar",
        "passport": "U4411107",
        "partner_passport": "U4411108",
        "room": "304",
    },
    {
        "first": "Mert",
        "partner": "Zeynep",
        "last": "Arslan",
        "phone": "+90 532 441 1109",
        "city": "Bakirkoy",
        "passport": "U4411109",
        "partner_passport": "U4411110",
        "room": "305",
    },
    {
        "first": "Kerem",
        "partner": "Lara",
        "last": "Acar",
        "phone": "+90 532 441 1111",
        "city": "Bebek",
        "passport": "U4411111",
        "partner_passport": "U4411112",
        "room": "306",
    },
    {
        "first": "Ozan",
        "partner": "Defne",
        "last": "Polat",
        "phone": "+90 532 441 1113",
        "city": "Ortakoy",
        "passport": "U4411113",
        "partner_passport": "U4411114",
        "room": "307",
    },
    {
        "first": "Baran",
        "partner": "Melis",
        "last": "Sen",
        "phone": "+90 532 441 1115",
        "city": "Cihangir",
        "passport": "U4411115",
        "partner_passport": "U4411116",
        "room": "308",
    },
    {
        "first": "Tolga",
        "partner": "Ipek",
        "last": "Kurt",
        "phone": "+90 532 441 1117",
        "city": "Moda",
        "passport": "U4411117",
        "partner_passport": "U4411118",
        "room": "309",
    },
    {
        "first": "Hakan",
        "partner": "Seda",
        "last": "Ucar",
        "phone": "+90 532 441 1119",
        "city": "Nisantasi",
        "passport": "U4411119",
        "partner_passport": "U4411120",
        "room": "310",
    },
    {
        "first": "Yigit",
        "partner": "Nil",
        "last": "Erdem",
        "phone": "+90 532 441 1121",
        "city": "Etiler",
        "passport": "U4411121",
        "partner_passport": "U4411122",
        "room": "311",
    },
)

SEED_PHOTOS = Path(__file__).resolve().parent.parent.parent / "seed_photos"
GALLERY = (
    ("istanbul-blue-mosque.png", "Sultanahmet and the Blue Mosque"),
    ("istanbul-hagia-sophia.png", "Hagia Sophia from the plaza"),
    ("istanbul-bosphorus.png", "Bosphorus ferry crossing"),
    ("istanbul-hotel.png", "Bosphorus Hotel courtyard"),
)


def _pay(booking, *, actor_id, method=PaymentMethod.CASH.value, reference=None):
    invoice = InvoiceService().repository.find_by_booking(booking["_id"])
    if not invoice:
        raise RuntimeError(f"No invoice for {booking.get('booking_number')}")
    snapshot = InvoiceService().money_snapshot(str(invoice["_id"]))
    return PaymentService().record_for_invoice(
        str(invoice["_id"]),
        amount=snapshot["remaining"],
        method=method,
        recorded_by=actor_id,
        reference_number=reference,
    )


class Command(BaseCommand):
    help = "Wipe business records and seed the Istanbul Escape presentation dataset (DEBUG only)."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Refusing to seed presentation data when DEBUG is False.")
        try:
            ensure_indexes()
        except DatabaseUnavailableError as extra:
            raise CommandError(str(extra)) from extra
        call_command("seed_demo_user")
        owner = User.objects.get(email=settings.DEMO_OWNER_EMAIL.strip().lower())
        agent = User.objects.get(email=settings.DEMO_AGENT_EMAIL.strip().lower())
        accountant = User.objects.get(email=settings.DEMO_ACCOUNTANT_EMAIL.strip().lower())
        self.owner_id = owner.actor_id
        self.agent_id = agent.actor_id
        self.accountant_id = accountant.actor_id

        for name in WIPE:
            get_collection(name).delete_many({})
        media = Path(settings.MEDIA_ROOT) / "attachments"
        if media.exists():
            shutil.rmtree(media, ignore_errors=True)
        self.stdout.write(self.style.WARNING("Deleted existing business records (including Cedar Routes demo data)."))

        SettingsService().update(
            actor_id=self.owner_id,
            agency_name="TourOps",
            legal_name="TourOps Travel",
            agency_email="hello@tourops.local",
            agency_phone="+90 212 000 0000",
            agency_address="Karakoy, Istanbul",
            currency="USD",
            tax_name="VAT",
            tax_rate=Decimal("0.00"),
            tax_enabled=False,
            invoice_due_days=14,
            number_start=1001,
        )

        catalog = self._catalog()
        tour = self._tour(catalog)
        self._gallery(tour)
        self._reservations_and_bookings(catalog, tour)
        self._expenses(catalog, tour)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Istanbul Escape is ready."))
        self.stdout.write("Open /presentation/ on each demo window, then Begin.")
        self.stdout.write("Maya Hassan is not created — add her live (2 travelers, Confirm & invoice).")
        self.stdout.write("Three supplier holds are REQUESTED. Confirm hotel and guide, then transport last.")

    def _catalog(self) -> dict:
        suppliers = SupplierService()
        offerings = SupplierOfferingService()
        packages = PackageService()
        owner = self.owner_id

        hotel = suppliers.create(
            actor_id=owner,
            name=STORY["hotel"],
            supplier_type=SupplierType.HOTEL.value,
            contact_person="Leyla Arslan",
            email="groups@bosphorushotel.example",
            phone="+90 212 555 0101",
            city="Istanbul",
            country="Turkey",
            street="Alemdar Caddesi 12, Sultanahmet",
            star_rating=4,
            tax_number="1234567890",
            preferred_payment_method=PaymentMethod.BANK_TRANSFER.value,
            bank_name="Garanti BBVA",
            account_name="Bosphorus Hotel A.S.",
            iban="TR33 0006 2000 0000 0066 7430 001",
            swift_bic="TGBATRIS",
            payment_terms="30% on confirmation, balance 14 days before arrival",
            notes="Group block on the courtyard wing. Twin rooms, breakfast included.",
        )
        transport = suppliers.create(
            actor_id=owner,
            name=STORY["transport"],
            supplier_type=SupplierType.TRANSPORTATION.value,
            contact_person="Ozan Kilic",
            email="ops@istanbultransport.example",
            phone="+90 212 555 0202",
            city="Istanbul",
            country="Turkey",
            street="Ataturk Airport Road, Bakirkoy",
            vehicle_type="Mercedes Sprinter",
            fleet_size=10,
            seats_per_vehicle=16,
            license_number="IST-TR-4410",
            coverage_areas="Istanbul airport, Sultanahmet, Bosphorus, old city",
            tax_number="3344556677",
            preferred_payment_method=PaymentMethod.BANK_TRANSFER.value,
            bank_name="Isbank",
            account_name="Istanbul Transport Ltd",
            iban="TR64 0006 4000 0011 2345 6789 01",
            swift_bic="ISBKTRIS",
            payment_terms="Net 7 after departure",
            notes="Airport arrivals plus daily touring coach for the same group.",
        )
        guide = suppliers.create(
            actor_id=owner,
            name=STORY["guide"],
            supplier_type=SupplierType.TOUR_GUIDE.value,
            contact_person="Defne Yilmaz",
            email="defne@istanbullocalguide.example",
            phone="+90 532 555 0303",
            city="Istanbul",
            country="Turkey",
            street="Cankurtaran, Fatih",
            languages="Turkish, English",
            specialties="Old city, Bosphorus, food",
            years_experience=12,
            license_number="MOT-GD-1509",
            preferred_payment_method=PaymentMethod.CASH.value,
            payment_terms="Cash on last touring day",
            notes="Licensed Ministry of Tourism guide. Meets the group at the hotel lobby.",
        )

        stay = offerings.create(
            actor_id=owner,
            supplier_id=hotel["_id"],
            name="Accommodation",
            service_kind=SupplierServiceKind.ACCOMMODATION.value,
            estimated_cost="9000.00",
            cost_basis=CostBasis.PER_GROUP.value,
            description="Fifteen twin rooms, Sultanahmet courtyard wing, five nights, breakfast included.",
            notes="Quoted for 30 pax sharing twins. Bosphorus Hotel group rate.",
        )
        airport = offerings.create(
            actor_id=owner,
            supplier_id=transport["_id"],
            name="Airport Transfer",
            service_kind=SupplierServiceKind.TRANSPORTATION.value,
            estimated_cost="1500.00",
            cost_basis=CostBasis.PER_GROUP.value,
            description="IST airport arrivals and departures for the group, Mercedes Sprinter.",
            notes="Meet-and-greet at arrivals. Same supplier as the daily coach.",
        )
        coach = offerings.create(
            actor_id=owner,
            supplier_id=transport["_id"],
            name="Full-Day Transportation",
            service_kind=SupplierServiceKind.TRANSPORTATION.value,
            estimated_cost="3000.00",
            cost_basis=CostBasis.PER_GROUP.value,
            description="Private touring coach for old city, Bosphorus, and hotel shuttles, six days.",
            notes="Driver and fuel included. Seats 16 per van; two vans if the group is full.",
        )
        city = offerings.create(
            actor_id=owner,
            supplier_id=guide["_id"],
            name="City Tour",
            service_kind=SupplierServiceKind.GUIDE.value,
            estimated_cost="2000.00",
            cost_basis=CostBasis.PER_GROUP.value,
            description="Licensed city guide for Sultanahmet, Grand Bazaar, and Bosphorus walking days.",
            notes="Defne Yilmaz, six touring days. Cash on the last evening.",
        )
        package = packages.create(
            actor_id=owner,
            name=STORY["package_name"],
            city="Istanbul",
            country="Turkey",
            duration_days=6,
            selling_price_per_person=STORY["price"],
            target_margin_percent="35.00",
            default_capacity=STORY["capacity"],
            description="Sultanahmet hotel, airport transfers, daily coach, and a licensed city guide — each line is a supplier service.",
            includes="Hotel, airport transfer, full-day coach, city tour",
            excluded="Flights, travel insurance, personal expenses",
            services=[
                {"supplier_service_id": stay["_id"]},
                {"supplier_service_id": airport["_id"]},
                {"supplier_service_id": coach["_id"]},
                {"supplier_service_id": city["_id"]},
            ],
        )
        for offering, owner_name in (
            (stay, hotel["name"]),
            (airport, transport["name"]),
            (coach, transport["name"]),
            (city, guide["name"]),
        ):
            if not offering.get("supplier_id"):
                raise CommandError(f"{offering.get('name')} was saved without a supplier.")
            presented = offerings.get_presented(offering["_id"])
            if presented.get("supplier") in ("", "—") or presented.get("supplier") != owner_name:
                raise CommandError(f"{offering.get('name')} is not attached to {owner_name}.")
        self.stdout.write("Catalog: 3 suppliers, 4 services (each on a supplier), 1 package.")
        presented_pkg = packages.get_presented(package["_id"])
        missing = [
            line.get("title") or line.get("name") or "service"
            for line in presented_pkg.get("services") or []
            if not line.get("supplier_id") or line.get("supplier") in ("", "—")
        ]
        if missing or len(presented_pkg.get("services") or []) != 4:
            raise CommandError(f"Package services are missing supplier links: {missing or 'count'}")
        return {
            "hotel": hotel,
            "transport": transport,
            "guide": guide,
            "package": package,
        }

    def _tour(self, catalog) -> dict:
        tour = TourService().create(
            actor_id=self.owner_id,
            package_id=catalog["package"]["_id"],
            name=STORY["tour_name"],
            start_date=STORY["start"],
            end_date=STORY["end"],
            capacity=STORY["capacity"],
            selling_price_per_person=STORY["price"],
        )
        self.stdout.write(f"Tour {tour.get('tour_code')} · {STORY['dates_label']} · {STORY['capacity']} seats.")
        return tour

    def _gallery(self, tour) -> None:
        service = AttachmentService()
        added = 0
        for filename, notes in GALLERY:
            path = SEED_PHOTOS / filename
            if not path.is_file():
                continue
            upload = SimpleUploadedFile(filename, path.read_bytes(), content_type="image/png")
            service.create(
                actor_id=self.owner_id,
                entity_type=AttachmentEntityType.TOURS.value,
                entity_id=tour["_id"],
                category=AttachmentCategory.GALLERY.value,
                upload=upload,
                notes=notes,
            )
            added += 1
        self.stdout.write(f"Gallery: {added} photos on the departure.")

    def _reservations_and_bookings(self, catalog, tour) -> None:
        reservations = SupplierReservationService()
        customers = CustomerService()
        rows = {
            "hotel": reservations.create(
                actor_id=self.agent_id,
                tour_id=tour["_id"],
                supplier_id=catalog["hotel"]["_id"],
                quantity=15,
                release_date="2026-09-08",
                notes="15 twins, courtyard wing, breakfast included. Guest of record on the block: group Istanbul Escape.",
                status=SupplierReservationStatus.CONFIRMED.value,
                confirmation_number="IST-HOT-SEED",
            ),
            "transport": reservations.create(
                actor_id=self.agent_id,
                tour_id=tour["_id"],
                supplier_id=catalog["transport"]["_id"],
                quantity=2,
                notes="Covers both catalog services: IST airport transfers ($1,500) and full-day touring coach ($3,000).",
                status=SupplierReservationStatus.CONFIRMED.value,
                confirmation_number="IST-TRN-SEED",
            ),
            "guide": reservations.create(
                actor_id=self.agent_id,
                tour_id=tour["_id"],
                supplier_id=catalog["guide"]["_id"],
                quantity=1,
                notes="Defne Yilmaz, six touring days. Meets the group in the Bosphorus Hotel lobby.",
                status=SupplierReservationStatus.CONFIRMED.value,
                confirmation_number="IST-GDE-SEED",
            ),
        }

        for index, household in enumerate(HOUSEHOLDS, start=1):
            customer = customers.create(
                actor_id=self.agent_id,
                first_name=household["first"],
                last_name=household["last"],
                email=f"{household['first'].lower()}.{household['last'].lower()}@example.com",
                phone=household["phone"],
                city=household["city"],
                country="Turkey",
                nationality="Turkish",
                passport=household["passport"],
                notes=f"Twin {household['room']} on Istanbul Escape. Travelling with {household['partner']} {household['last']}.",
            )
            booking = BookingService().create(
                actor_id=self.agent_id,
                customer_id=customer["_id"],
                tour_id=tour["_id"],
                travelers=[
                    {
                        "first_name": household["first"],
                        "last_name": household["last"],
                        "passport_number": household["passport"],
                        "nationality": "Turkish",
                        "room_type": "TWIN",
                        "room_number": household["room"],
                    },
                    {
                        "first_name": household["partner"],
                        "last_name": household["last"],
                        "passport_number": household["partner_passport"],
                        "nationality": "Turkish",
                        "room_type": "TWIN",
                        "room_number": household["room"],
                    },
                ],
                notes=f"Paid household. Twin {household['room']}.",
            )
            booking = BookingService().confirm(booking["_id"], actor_id=self.agent_id)
            _pay(
                booking,
                actor_id=self.accountant_id,
                method=PaymentMethod.BANK_TRANSFER.value,
                reference=f"IST-BG-{index:02d}",
            )

        for row in rows.values():
            reservations.update(
                row["_id"],
                actor_id=self.owner_id,
                status=SupplierReservationStatus.REQUESTED.value,
                confirmation_number="",
            )
        self.stdout.write("22 seats paid. Holds reset to REQUESTED for the live confirmation beat.")

    def _expenses(self, catalog, tour) -> None:
        expenses = ExpenseService()
        owner = self.owner_id
        expenses.create(
            actor_id=owner,
            expense_scope=ExpenseScope.TOUR.value,
            category=ExpenseCategory.HOTEL.value,
            amount="9000.00",
            description="Bosphorus Hotel block, 15-20 Sep",
            expense_date="2026-08-20",
            due_date="2026-09-10",
            supplier_id=catalog["hotel"]["_id"],
            tour_id=tour["_id"],
        )
        expenses.create(
            actor_id=owner,
            expense_scope=ExpenseScope.TOUR.value,
            category=ExpenseCategory.TRANSPORTATION.value,
            amount="4500.00",
            description="Airport transfers and full-day coach",
            expense_date="2026-08-20",
            due_date="2026-09-12",
            supplier_id=catalog["transport"]["_id"],
            tour_id=tour["_id"],
        )
        expenses.create(
            actor_id=owner,
            expense_scope=ExpenseScope.TOUR.value,
            category=ExpenseCategory.TOUR_GUIDE.value,
            amount="2000.00",
            description="Licensed city guide, six days",
            expense_date=STORY["start"],
            due_date="2026-09-20",
            supplier_id=catalog["guide"]["_id"],
            tour_id=tour["_id"],
        )
        expenses.create(
            actor_id=owner,
            expense_scope=ExpenseScope.TOUR.value,
            category=ExpenseCategory.MARKETING.value,
            amount="2000.00",
            description="Istanbul Escape brochure and ads (agency card — no supplier)",
            expense_date="2026-08-15",
            tour_id=tour["_id"],
        )
        self.stdout.write("Costs: $9,000 hotel, $4,500 transport, $2,000 guide, $2,000 other.")
