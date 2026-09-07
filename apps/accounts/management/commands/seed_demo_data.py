"""Replace Mongo business records with a realistic Cedar Routes Travel demo."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.accounts.settings_service import SettingsService
from apps.bookings.services import BookingService
from apps.customers.services import CustomerService
from apps.expenses.services import ExpenseService
from apps.invoices.services import InvoiceService
from apps.packages.services import PackageService
from apps.payments.services import PaymentService
from apps.refunds.services import RefundService
from apps.supplier_payments.services import SupplierPaymentService
from apps.supplier_reservations.services import SupplierReservationService
from apps.suppliers.offerings import SupplierOfferingService
from apps.suppliers.services import SupplierService
from apps.tours.services import TourService
from core.constants import (
    Collections,
    ExpenseCategory,
    ExpenseScope,
    PaymentMethod,
    RefundPolicyTier,
    SupplierReservationStatus,
    SupplierServiceKind,
    SupplierType,
    TourStatus,
)
from core.database import get_collection
from core.exceptions import DatabaseUnavailableError
from core.indexes import ensure_indexes
from core.money import to_money

WIPE_COLLECTIONS = (
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


def _people(*rows) -> list[dict]:
    people = []
    for row in rows:
        if isinstance(row, str):
            first, last = row.split(" ", 1)
            person = {"first_name": first, "last_name": last}
        else:
            person = dict(row)
        people.append(person)
    return people


def _invoice_for(booking) -> dict:
    invoice = InvoiceService().repository.find_by_booking(booking["_id"])
    if not invoice:
        raise RuntimeError(f"No invoice for booking {booking.get('booking_number')}")
    return invoice


def _pay(booking, *, actor_id, amount=None, method=PaymentMethod.CASH.value, reference=None):
    invoice = _invoice_for(booking)
    invoice_id = str(invoice["_id"])
    remaining = InvoiceService().money_snapshot(invoice_id)["remaining"]
    pay_amount = remaining if amount is None else to_money(amount)
    return PaymentService().record_for_invoice(
        invoice_id,
        amount=pay_amount,
        method=method,
        recorded_by=actor_id,
        reference_number=reference,
    )


class Command(BaseCommand):
    help = "Wipe business Mongo records and seed a realistic Cedar Routes Travel demo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep-existing",
            action="store_true",
            help="Do not delete current business records (not recommended for demos).",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Refusing to seed demo data when DEBUG is False.")
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

        if not options["keep_existing"]:
            self._wipe()
            self.stdout.write(self.style.WARNING("Deleted existing business records."))

        SettingsService().update(
            actor_id=self.owner_id,
            agency_name="Cedar Routes Travel",
            legal_name="Cedar Routes Travel SAL",
            agency_email="hello@cedarroutes.travel",
            agency_phone="+961 1 345 880",
            agency_address="42 Hamra Street, Beirut, Lebanon",
            currency="USD",
            tax_name="VAT",
            tax_rate=Decimal("11.00"),
            tax_enabled=True,
            invoice_due_days=14,
            number_start=1001,
        )
        self.stdout.write("Agency: Cedar Routes Travel SAL, Hamra, Beirut.")

        catalog = self._seed_catalog()
        customers = self._seed_customers()
        tours = self._seed_tours(catalog)
        self._seed_reservations(catalog, tours)
        self._seed_bookings_and_money(catalog, customers, tours)
        self._seed_expenses(catalog, tours)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Cedar Routes demo data is ready."))
        self.stdout.write("Logins (password changeme):")
        self.stdout.write(f"  Owner       {owner.email}  - {owner.get_full_name()}")
        self.stdout.write(f"  Agent       {agent.email}  - {agent.get_full_name()}")
        self.stdout.write(f"  Accountant  {accountant.email}  - {accountant.get_full_name()}")
        self.stdout.write("")
        self.stdout.write("Live demo hooks (leave these for the presentation):")
        self.stdout.write("  * Yasmin Farhat - PENDING booking on Lebanon 12-18 Sep (confirm + collect at desk)")
        self.stdout.write("  * Layla Mansour - CONFIRMED unpaid invoice (accountant collects remaining)")
        self.stdout.write("  * Elie Tannous - CONFIRMED partial payment (collect the rest)")
        self.stdout.write("  * Tania Harb - PENDING refund waiting for owner approval")
        self.stdout.write("  * Lebanon 3-9 Oct - suppliers still REQUESTED; cannot book until Phoenicia confirms")
        self.stdout.write("  * Phoenicia hotel expense still unpaid (pay the supplier)")
        self.stdout.write("  * Petra Nov departure is quiet - book a new family live")

    def _wipe(self) -> None:
        for name in WIPE_COLLECTIONS:
            get_collection(name).delete_many({})

    def _seed_catalog(self) -> dict:
        suppliers = SupplierService()
        offerings = SupplierOfferingService()
        packages = PackageService()
        owner = self.owner_id

        phoenicia = suppliers.create(
            actor_id=owner,
            name="Phoenicia Beirut",
            supplier_type=SupplierType.HOTEL.value,
            contact_person="Nadine Chami",
            email="groups@phoenicia-beirut.example",
            phone="+961 1 369 100",
            city="Beirut",
            country="Lebanon",
            street="Minet El Hosn",
            star_rating=5,
            preferred_payment_method=PaymentMethod.BANK_TRANSFER.value,
            bank_name="Bank Audi",
            account_name="Phoenicia Beirut SAL",
            iban="LB62 0056 0000 0001 2345 6789 0123",
            swift_bic="AUDBLBBX",
            payment_terms="30% on confirmation, balance 14 days before arrival",
            tax_number="601-445890",
        )
        liban_coach = suppliers.create(
            actor_id=owner,
            name="Liban Coach",
            supplier_type=SupplierType.TRANSPORTATION.value,
            contact_person="Walid Sfeir",
            email="ops@libancoach.example",
            phone="+961 3 220 441",
            city="Beirut",
            country="Lebanon",
            street="Industrial City, Mkalles",
            vehicle_type="Mercedes Sprinter",
            fleet_size=12,
            seats_per_vehicle=16,
            license_number="LB-TR-8841",
            coverage_areas="Beirut, Mount Lebanon, Bekaa, South",
            preferred_payment_method=PaymentMethod.BANK_TRANSFER.value,
            bank_name="BLOM Bank",
            account_name="Liban Coach SARL",
            iban="LB14 0014 0000 0009 8765 4321 0001",
            swift_bic="BLOMLBBX",
            payment_terms="Net 7 after each departure",
        )
        maya = suppliers.create(
            actor_id=owner,
            name="Maya Haddad Guiding",
            supplier_type=SupplierType.TOUR_GUIDE.value,
            contact_person="Maya Haddad",
            email="maya@haddadguides.example",
            phone="+961 3 551 902",
            city="Beirut",
            country="Lebanon",
            languages="Arabic, English, French",
            specialties="Heritage, food, family groups",
            years_experience=11,
            license_number="MOT-GD-2044",
            preferred_payment_method=PaymentMethod.CASH.value,
            payment_terms="Cash on last touring day",
        )
        jeita = suppliers.create(
            actor_id=owner,
            name="Jeita & Byblos Experiences",
            supplier_type=SupplierType.ACTIVITY_PROVIDER.value,
            contact_person="Elie Bou Saab",
            email="desk@jeitabyblos.example",
            phone="+961 9 220 840",
            city="Jeita",
            country="Lebanon",
            activity_kinds="Cave visit, coastal boat",
            typical_duration_hours=5,
            location="Jeita Grotto and Byblos harbour",
            preferred_payment_method=PaymentMethod.BANK_TRANSFER.value,
            payment_terms="Prepaid 48 hours before",
            bank_name="Bank of Beirut",
            account_name="Jeita & Byblos Experiences SARL",
            iban="LB70 0075 0000 0001 1122 3344 5566",
            swift_bic="BABELBBE",
        )
        tawlet = suppliers.create(
            actor_id=owner,
            name="Tawlet Mar Mikhael",
            supplier_type=SupplierType.RESTAURANT.value,
            contact_person="Kamal Mouzawak",
            email="groups@tawlet.example",
            phone="+961 1 448 129",
            city="Beirut",
            country="Lebanon",
            cuisine="Lebanese village",
            seating_capacity=70,
            meal_types="Lunch",
            preferred_payment_method=PaymentMethod.CASH.value,
            payment_terms="Cash on the day",
        )
        ishtar = suppliers.create(
            actor_id=owner,
            name="Kempinski Hotel Ishtar Dead Sea",
            supplier_type=SupplierType.HOTEL.value,
            contact_person="Hana Al-Majali",
            email="groups@kempinski-ishtar.example",
            phone="+962 5 356 0000",
            city="Sweimeh",
            country="Jordan",
            street="Dead Sea Road",
            star_rating=5,
            preferred_payment_method=PaymentMethod.BANK_TRANSFER.value,
            bank_name="Arab Bank",
            account_name="Kempinski Hotels Jordan",
            iban="JO94 ARAB 1234 5678 9012 3456 7890",
            swift_bic="ARABJOAX",
            payment_terms="One night deposit, balance 21 days before",
        )
        petra_trail = suppliers.create(
            actor_id=owner,
            name="Petra Trail Transport",
            supplier_type=SupplierType.TRANSPORTATION.value,
            contact_person="Ziad Qudah",
            email="ops@petratrail.example",
            phone="+962 79 555 2210",
            city="Amman",
            country="Jordan",
            vehicle_type="Toyota Coaster",
            fleet_size=8,
            seats_per_vehicle=21,
            license_number="JO-TR-2291",
            coverage_areas="Amman, Dead Sea, Petra, Wadi Rum",
            preferred_payment_method=PaymentMethod.BANK_TRANSFER.value,
            bank_name="Cairo Amman Bank",
            account_name="Petra Trail Transport",
            iban="JO22 CAAB 0000 0000 1111 2222 3333",
            swift_bic="CAABJOAM",
            payment_terms="Net 14 before departure",
        )
        nour = suppliers.create(
            actor_id=owner,
            name="Nour Al-Faris Guiding",
            supplier_type=SupplierType.TOUR_GUIDE.value,
            contact_person="Nour Al-Faris",
            email="nour@alfarisguides.example",
            phone="+962 79 441 8830",
            city="Wadi Musa",
            country="Jordan",
            languages="Arabic, English",
            specialties="Petra, Wadi Rum, biblical sites",
            years_experience=9,
            license_number="JTB-GD-1188",
            preferred_payment_method=PaymentMethod.BANK_TRANSFER.value,
            bank_name="Arab Bank",
            account_name="Nour Al-Faris Guiding",
            iban="JO94 ARAB 0000 1111 2222 3333 4444",
            swift_bic="ARABJOAX",
            payment_terms="Net 7 after the last touring day",
        )

        phoenicia_stay = offerings.create(
            actor_id=owner,
            supplier_id=phoenicia["_id"],
            name="Twin BB — 6 nights, city and harbour view",
            service_kind=SupplierServiceKind.ACCOMMODATION.value,
            estimated_cost="540.00",
            cost_basis="PER_PERSON",
            description="Per person share of a twin, bed and breakfast, Minet El Hosn.",
        )
        lebanon_coach = offerings.create(
            actor_id=owner,
            supplier_id=liban_coach["_id"],
            name="Airport arrivals plus daily touring coach",
            service_kind=SupplierServiceKind.TRANSPORTATION.value,
            estimated_cost="2400.00",
            cost_basis="PER_GROUP",
            description="Mercedes Sprinter with driver, 7 touring days.",
        )
        lebanon_guide = offerings.create(
            actor_id=owner,
            supplier_id=maya["_id"],
            name="Licensed guide, 7 touring days",
            service_kind=SupplierServiceKind.GUIDE.value,
            estimated_cost="1050.00",
            cost_basis="PER_GROUP",
            description="Maya Haddad, licensed heritage guide, seven touring days.",
        )
        lebanon_activity = offerings.create(
            actor_id=owner,
            supplier_id=jeita["_id"],
            name="Jeita Grotto tickets and Byblos boat",
            service_kind=SupplierServiceKind.ACTIVITY.value,
            estimated_cost="900.00",
            cost_basis="PER_GROUP",
        )
        lebanon_lunch = offerings.create(
            actor_id=owner,
            supplier_id=tawlet["_id"],
            name="Village lunch for the group, 18 pax",
            service_kind=SupplierServiceKind.MEAL.value,
            estimated_cost="620.00",
            cost_basis="PER_GROUP",
        )
        dead_sea_stay = offerings.create(
            actor_id=owner,
            supplier_id=ishtar["_id"],
            name="Garden-view twin, half board, 5 nights",
            service_kind=SupplierServiceKind.ACCOMMODATION.value,
            estimated_cost="725.00",
            cost_basis="PER_PERSON",
            description="Per person share of a twin, half board.",
        )
        jordan_coach = offerings.create(
            actor_id=owner,
            supplier_id=petra_trail["_id"],
            name="Amman–Dead Sea–Petra–Wadi Rum circuit",
            service_kind=SupplierServiceKind.TRANSPORTATION.value,
            estimated_cost="2650.00",
            cost_basis="PER_GROUP",
        )
        jordan_guide = offerings.create(
            actor_id=owner,
            supplier_id=nour["_id"],
            name="Petra and Wadi Rum licensed guide, 6 days",
            service_kind=SupplierServiceKind.GUIDE.value,
            estimated_cost="1200.00",
            cost_basis="PER_GROUP",
            description="Nour Al-Faris, licensed Petra and Wadi Rum guide, six days.",
        )

        lebanon_pkg = packages.create(
            actor_id=owner,
            name="Lebanon Discovery 7D",
            city="Beirut",
            country="Lebanon",
            duration_days=7,
            selling_price_per_person="1250.00",
            target_margin_percent="30.00",
            default_capacity=18,
            description=(
                "Beirut, Jeita, Byblos, Beiteddine, and Baalbek with a harbour hotel, "
                "private coach, and a licensed guide."
            ),
            includes="Harbour hotel BB, private coach, licensed guide, Jeita & Byblos, one village lunch",
            excluded="Flights, travel insurance, personal expenses",
            services=[
                {"supplier_service_id": phoenicia_stay["_id"]},
                {"supplier_service_id": lebanon_coach["_id"]},
                {"supplier_service_id": lebanon_guide["_id"]},
                {"supplier_service_id": lebanon_activity["_id"]},
                {"supplier_service_id": lebanon_lunch["_id"]},
            ],
        )
        jordan_pkg = packages.create(
            actor_id=owner,
            name="Petra, Wadi Rum & the Dead Sea 6D",
            city="Amman",
            country="Jordan",
            duration_days=6,
            selling_price_per_person="1580.00",
            target_margin_percent="30.00",
            default_capacity=16,
            description=(
                "Amman arrival, two nights at the Dead Sea, a full day in Petra, "
                "and a Wadi Rum camp evening before the drive back."
            ),
            includes="Dead Sea hotel half board, private coach, licensed guide, Petra tickets handled by the guide",
            excluded="Flights, travel insurance, Wadi Rum jeep upgrade",
            services=[
                {"supplier_service_id": dead_sea_stay["_id"]},
                {"supplier_service_id": jordan_coach["_id"]},
                {"supplier_service_id": jordan_guide["_id"]},
            ],
        )
        self.stdout.write("Catalog: 8 suppliers, 8 services, 2 packages.")
        return {
            "phoenicia": phoenicia,
            "liban_coach": liban_coach,
            "maya": maya,
            "jeita": jeita,
            "tawlet": tawlet,
            "ishtar": ishtar,
            "petra_trail": petra_trail,
            "nour": nour,
            "lebanon_pkg": lebanon_pkg,
            "jordan_pkg": jordan_pkg,
        }

    def _seed_customers(self) -> dict:
        agent = self.agent_id
        customers = CustomerService()

        def add(**fields):
            return customers.create(actor_id=agent, **fields)

        records = {
            "nadine": add(
                first_name="Nadine",
                last_name="Khoury",
                email="nadine.khoury@example.com",
                phone="+961 3 441 228",
                city="Achrafieh",
                country="Lebanon",
                nationality="Lebanese",
                passport="LR2054412",
                notes="Books family trips around school holidays. Prefers a twin near the lift.",
            ),
            "samer": add(
                first_name="Samer",
                last_name="Abou Jaoude",
                email="samer.aj@example.com",
                phone="+961 3 778 094",
                city="Broummana",
                country="Lebanon",
                nationality="Lebanese",
                passport="LR1882301",
            ),
            "layla": add(
                first_name="Layla",
                last_name="Mansour",
                email="layla.mansour@example.com",
                phone="+961 6 430 112",
                city="Tripoli",
                country="Lebanon",
                nationality="Lebanese",
                passport="LR1766509",
                notes="Will settle by bank transfer from Bank of Beirut.",
            ),
            "omar": add(
                first_name="Omar",
                last_name="Al-Masri",
                email="omar.almasri@example.com",
                phone="+962 79 662 1144",
                city="Amman",
                country="Jordan",
                nationality="Jordanian",
                passport="JO4459012",
            ),
            "hiba": add(
                first_name="Hiba",
                last_name="Rahme",
                email="hiba.rahme@example.com",
                phone="+961 3 902 441",
                city="Verdun",
                country="Lebanon",
                nationality="Lebanese",
                passport="LR2210988",
            ),
            "fadi": add(
                first_name="Fadi",
                last_name="Sleiman",
                email="fadi.sleiman@example.com",
                phone="+961 3 115 670",
                city="Jounieh",
                country="Lebanon",
                nationality="Lebanese",
                passport="LR1993340",
            ),
            "ghossoub": add(
                first_name="Joumana",
                last_name="Ghossoub",
                email="joumana.ghossoub@example.com",
                phone="+961 3 334 808",
                city="Rabieh",
                country="Lebanon",
                nationality="Lebanese",
                passport="LR1542290",
                notes="Travelling with two teenagers. Needs connecting twins.",
            ),
            "elie": add(
                first_name="Elie",
                last_name="Tannous",
                email="elie.tannous@example.com",
                phone="+961 3 667 221",
                city="Zahle",
                country="Lebanon",
                nationality="Lebanese",
                passport="LR2087711",
            ),
            "yasmin": add(
                first_name="Yasmin",
                last_name="Farhat",
                email="yasmin.farhat@example.com",
                phone="+961 3 880 145",
                city="Hamra",
                country="Lebanon",
                nationality="Lebanese",
                passport="LR2304418",
                notes="Walk-in from the Hamra office. Waiting on her husband's passport scan.",
            ),
            "tania": add(
                first_name="Tania",
                last_name="Harb",
                email="tania.harb@example.com",
                phone="+961 3 229 774",
                city="Baabda",
                country="Lebanon",
                nationality="Lebanese",
                passport="LR1678803",
                notes="Asked to postpone Petra. Refund request is with accounts.",
            ),
            "ramzi": add(
                first_name="Ramzi",
                last_name="Nassar",
                email="ramzi.nassar@example.com",
                phone="+961 3 501 992",
                city="Antelias",
                country="Lebanon",
                nationality="Lebanese",
                passport="LR1420095",
            ),
        }
        self.stdout.write(f"Customers: {len(records)} household files.")
        return records

    def _seed_tours(self, catalog: dict) -> dict:
        tours = TourService()
        owner = self.owner_id
        lebanon = catalog["lebanon_pkg"]["_id"]
        jordan = catalog["jordan_pkg"]["_id"]

        august = tours.create(
            actor_id=owner,
            package_id=lebanon,
            name="Lebanon Discovery 7D",
            start_date="2026-08-08",
            end_date="2026-08-14",
            capacity=18,
        )
        in_progress = tours.create(
            actor_id=owner,
            package_id=lebanon,
            name="Lebanon Discovery 7D",
            start_date="2026-09-02",
            end_date="2026-09-08",
            capacity=18,
        )
        september = tours.create(
            actor_id=owner,
            package_id=lebanon,
            name="Lebanon Discovery 7D",
            start_date="2026-09-12",
            end_date="2026-09-18",
            capacity=18,
        )
        october = tours.create(
            actor_id=owner,
            package_id=lebanon,
            name="Lebanon Discovery 7D",
            start_date="2026-10-03",
            end_date="2026-10-09",
            capacity=18,
        )
        petra_sep = tours.create(
            actor_id=owner,
            package_id=jordan,
            name="Petra, Wadi Rum & the Dead Sea 6D",
            start_date="2026-09-20",
            end_date="2026-09-25",
            capacity=16,
        )
        petra_nov = tours.create(
            actor_id=owner,
            package_id=jordan,
            name="Petra, Wadi Rum & the Dead Sea 6D",
            start_date="2026-11-22",
            end_date="2026-11-27",
            capacity=16,
        )
        self.stdout.write("Departures: 4 Lebanon + 2 Jordan.")
        return {
            "august": august,
            "in_progress": in_progress,
            "september": september,
            "october": october,
            "petra_sep": petra_sep,
            "petra_nov": petra_nov,
        }

    def _book(self, tour, customer, travelers, *, confirm=False, notes=None):
        booking = BookingService().create(
            actor_id=self.agent_id,
            customer_id=customer["_id"],
            tour_id=tour["_id"],
            travelers=_people(*travelers),
            notes=notes,
        )
        if confirm:
            booking = BookingService().confirm(booking["_id"], actor_id=self.agent_id)
        return booking

    def _seed_bookings_and_money(self, catalog, customers, tours) -> None:
        agent = self.agent_id
        accountant = self.accountant_id
        owner = self.owner_id

        # Past Lebanon — paid in full, then mark the departure completed.
        ramzi = self._book(
            tours["august"],
            customers["ramzi"],
            [
                {"first_name": "Ramzi", "last_name": "Nassar", "passport_number": "LR1420095", "room_type": "DOUBLE", "room_number": "812"},
                {"first_name": "Maya", "last_name": "Nassar", "passport_number": "LR1420096", "room_type": "DOUBLE", "room_number": "812"},
                {"first_name": "Tony", "last_name": "Nassar", "passport_number": "LR1420097", "room_type": "SINGLE", "room_number": "814"},
            ],
            confirm=True,
            notes="Anniversary trip. Paid in cash at the Hamra desk before departure.",
        )
        _pay(ramzi, actor_id=agent, method=PaymentMethod.CASH.value, reference="CASH-AUG-RAMZI")
        hiba_aug = self._book(
            tours["august"],
            customers["hiba"],
            [
                {"first_name": "Hiba", "last_name": "Rahme", "passport_number": "LR2210988", "room_type": "TWIN", "room_number": "820"},
                {"first_name": "Rana", "last_name": "Rahme", "passport_number": "LR2210989", "room_type": "TWIN", "room_number": "820"},
            ],
            confirm=True,
        )
        _pay(hiba_aug, actor_id=accountant, method=PaymentMethod.BANK_TRANSFER.value, reference="BOB-88421")
        TourService().update(tours["august"]["_id"], actor_id=owner, status=TourStatus.COMPLETED.value)

        # Currently on the road.
        fadi = self._book(
            tours["in_progress"],
            customers["fadi"],
            [
                {"first_name": "Fadi", "last_name": "Sleiman", "passport_number": "LR1993340", "room_type": "DOUBLE", "room_number": "504"},
                {"first_name": "Rana", "last_name": "Sleiman", "passport_number": "LR1993341", "room_type": "DOUBLE", "room_number": "504"},
            ],
            confirm=True,
        )
        _pay(fadi, actor_id=agent, method=PaymentMethod.CARD.value, reference="POS-SEP02")
        samer_now = self._book(
            tours["in_progress"],
            customers["samer"],
            [
                {"first_name": "Samer", "last_name": "Abou Jaoude", "passport_number": "LR1882301", "room_type": "TWIN", "room_number": "506"},
                {"first_name": "Marc", "last_name": "Abou Jaoude", "passport_number": "LR1882302", "room_type": "TWIN", "room_number": "506"},
                {"first_name": "Lara", "last_name": "Abou Jaoude", "passport_number": "LR1882303", "room_type": "SINGLE", "room_number": "507"},
            ],
            confirm=True,
        )
        _pay(samer_now, actor_id=accountant, method=PaymentMethod.BANK_TRANSFER.value, reference="BLF-99210")
        TourService().update(tours["in_progress"]["_id"], actor_id=owner, status=TourStatus.IN_PROGRESS.value)

        # 12–18 Sep — nearly full, mixed money. 16 confirmed seats, 2 pending.
        ghossoub = self._book(
            tours["september"],
            customers["ghossoub"],
            [
                {"first_name": "Joumana", "last_name": "Ghossoub", "passport_number": "LR1542290", "room_type": "TWIN", "room_number": "1102"},
                {"first_name": "Karim", "last_name": "Ghossoub", "passport_number": "LR1542291", "room_type": "TWIN", "room_number": "1102"},
                {"first_name": "Nour", "last_name": "Ghossoub", "passport_number": "LR1542292", "room_type": "SINGLE", "room_number": "1104"},
            ],
            confirm=True,
            notes="Connecting twins if the hotel can. Teenagers, no extra bed.",
        )
        _pay(ghossoub, actor_id=agent, method=PaymentMethod.CASH.value, reference="CASH-GHOSSOUB")
        sleiman_sep = self._book(
            tours["september"],
            customers["fadi"],
            [
                {"first_name": "Elie", "last_name": "Sleiman", "passport_number": "LR1993402", "room_type": "DOUBLE"},
                {"first_name": "Paula", "last_name": "Sleiman", "passport_number": "LR1993403", "room_type": "DOUBLE"},
            ],
            confirm=True,
            notes="Fadi's brother — second household on the same departure.",
        )
        _pay(sleiman_sep, actor_id=accountant, method=PaymentMethod.BANK_TRANSFER.value, reference="BOB-11092")
        hiba_sep = self._book(
            tours["september"],
            customers["hiba"],
            [
                {"first_name": "Hiba", "last_name": "Rahme", "passport_number": "LR2210988", "room_type": "TWIN"},
                {"first_name": "Yara", "last_name": "Rahme", "passport_number": "LR2210990", "room_type": "TWIN"},
            ],
            confirm=True,
        )
        _pay(hiba_sep, actor_id=agent, method=PaymentMethod.CARD.value, reference="POS-HIBA-SEP")
        nadine = self._book(
            tours["september"],
            customers["nadine"],
            [
                {"first_name": "Nadine", "last_name": "Khoury", "passport_number": "LR2054412", "room_type": "TWIN"},
                {"first_name": "Tarek", "last_name": "Khoury", "passport_number": "LR2054413", "room_type": "TWIN"},
            ],
            confirm=True,
        )
        _pay(nadine, actor_id=agent, method=PaymentMethod.CASH.value, reference="CASH-NADINE")
        elie = self._book(
            tours["september"],
            customers["elie"],
            [
                {"first_name": "Elie", "last_name": "Tannous", "passport_number": "LR2087711", "room_type": "DOUBLE"},
                {"first_name": "Rita", "last_name": "Tannous", "passport_number": "LR2087712", "room_type": "DOUBLE"},
            ],
            confirm=True,
            notes="Left a cash deposit. Balance promised before Friday.",
        )
        _pay(elie, actor_id=agent, amount="1500.00", method=PaymentMethod.CASH.value, reference="CASH-ELIE-DEP")
        layla = self._book(
            tours["september"],
            customers["layla"],
            [
                {"first_name": "Layla", "last_name": "Mansour", "passport_number": "LR1766509", "room_type": "TWIN"},
                {"first_name": "Hala", "last_name": "Mansour", "passport_number": "LR1766510", "room_type": "TWIN"},
            ],
            confirm=True,
            notes="Invoice issued. Waiting on the Bank of Beirut transfer.",
        )
        ramzi_sep = self._book(
            tours["september"],
            customers["ramzi"],
            [
                {"first_name": "Sami", "last_name": "Nassar", "passport_number": "LR1420101", "room_type": "DOUBLE"},
                {"first_name": "Lina", "last_name": "Nassar", "passport_number": "LR1420102", "room_type": "DOUBLE"},
                {"first_name": "Joe", "last_name": "Nassar", "passport_number": "LR1420103", "room_type": "SINGLE"},
            ],
            confirm=True,
            notes="Ramzi sending his brother this time.",
        )
        _pay(ramzi_sep, actor_id=accountant, method=PaymentMethod.BANK_TRANSFER.value, reference="BLF-SEP-SAMI")
        self._book(
            tours["september"],
            customers["yasmin"],
            [
                {"first_name": "Yasmin", "last_name": "Farhat", "passport_number": "LR2304418", "room_type": "DOUBLE"},
                {"first_name": "Bassam", "last_name": "Farhat", "room_type": "DOUBLE"},
            ],
            confirm=False,
            notes="Pending passport scan for Bassam. Two seats still free on this departure.",
        )

        # Petra September — open AR.
        omar_petra = self._book(
            tours["petra_sep"],
            customers["omar"],
            [
                {"first_name": "Omar", "last_name": "Al-Masri", "passport_number": "JO4459012", "room_type": "DOUBLE"},
                {"first_name": "Laila", "last_name": "Al-Masri", "passport_number": "JO4459013", "room_type": "DOUBLE"},
            ],
            confirm=True,
        )
        samer_petra = self._book(
            tours["petra_sep"],
            customers["samer"],
            [
                {"first_name": "Samer", "last_name": "Abou Jaoude", "passport_number": "LR1882301", "room_type": "TWIN"},
                {"first_name": "Marc", "last_name": "Abou Jaoude", "passport_number": "LR1882302", "room_type": "TWIN"},
                {"first_name": "Lara", "last_name": "Abou Jaoude", "passport_number": "LR1882303", "room_type": "SINGLE"},
                {"first_name": "Nada", "last_name": "Abou Jaoude", "passport_number": "LR1882304", "room_type": "SINGLE"},
            ],
            confirm=True,
            notes="Family of four. Deposit taken; balance due 7 days before.",
        )
        _pay(samer_petra, actor_id=agent, amount="2500.00", method=PaymentMethod.CASH.value, reference="CASH-PETRA-AJ")

        # Petra November — paid, then owner issued a full agency-cancel refund and cancelled.
        cancelled = self._book(
            tours["petra_nov"],
            customers["nadine"],
            [
                {"first_name": "Nadine", "last_name": "Khoury", "passport_number": "LR2054412", "room_type": "TWIN"},
                {"first_name": "Tarek", "last_name": "Khoury", "passport_number": "LR2054413", "room_type": "TWIN"},
            ],
            confirm=True,
            notes="Dates no longer work. Agency cancelled and returned the payment.",
        )
        paid = _pay(cancelled, actor_id=agent, method=PaymentMethod.CARD.value, reference="POS-NADINE-NOV")
        RefundService().create_from_payment(
            paid["id"],
            reason="Agency cancelled the November Petra departure for this couple after a date clash with a wedding.",
            refund_method=PaymentMethod.BANK_TRANSFER.value,
            requested_by=owner,
            tier=RefundPolicyTier.AGENCY_CANCEL.value,
            direct=True,
        )
        BookingService().cancel(cancelled["_id"], actor_id=agent)

        # Tania — paid Petra November, accountant requested a 90% refund (30+ days). Owner has not approved yet.
        tania = self._book(
            tours["petra_nov"],
            customers["tania"],
            [
                {"first_name": "Tania", "last_name": "Harb", "passport_number": "LR1678803", "room_type": "DOUBLE"},
                {"first_name": "Walid", "last_name": "Harb", "passport_number": "LR1678804", "room_type": "DOUBLE"},
            ],
            confirm=True,
            notes="Asked to drop out. Refund request sitting with the owner.",
        )
        tania_pay = _pay(tania, actor_id=accountant, method=PaymentMethod.BANK_TRANSFER.value, reference="BOB-TANIA-NOV")
        RefundService().create_from_payment(
            tania_pay["id"],
            reason="Couple cannot travel in November. Policy tier 30+ days (90%).",
            refund_method=PaymentMethod.BANK_TRANSFER.value,
            requested_by=accountant,
            tier=RefundPolicyTier.DAYS_30_PLUS.value,
            direct=False,
        )
        self.stdout.write("Bookings, invoices, payments, receipts, and refunds seeded.")

    def _seed_reservations(self, catalog, tours) -> None:
        reservations = SupplierReservationService()
        agent = self.agent_id
        lebanon = ("phoenicia", "liban_coach", "maya", "jeita", "tawlet")
        jordan = ("ishtar", "petra_trail", "nour")

        def arrange(tour, keys, *, requested=(), extras=None):
            extras = extras or {}
            code = tour.get("tour_code") or str(tour["_id"])[-6:]
            for key in keys:
                payload = {
                    "actor_id": agent,
                    "tour_id": tour["_id"],
                    "supplier_id": catalog[key]["_id"],
                    **extras.get(key, {}),
                }
                if key in requested:
                    payload["status"] = SupplierReservationStatus.REQUESTED.value
                    payload.pop("confirmation_number", None)
                else:
                    payload.setdefault("status", SupplierReservationStatus.CONFIRMED.value)
                    payload.setdefault("confirmation_number", f"{key[:4].upper()}-{code}")
                reservations.create(**payload)

        arrange(
            tours["august"],
            lebanon,
            extras={
                "phoenicia": {
                    "confirmation_number": "PHX-AUG-4410",
                    "release_date": "2026-07-25",
                    "quantity": 5,
                    "notes": "All rooms used. Group checked out 14 Aug.",
                }
            },
        )
        arrange(
            tours["in_progress"],
            lebanon,
            extras={
                "phoenicia": {"confirmation_number": "PHX-SEP02-118", "quantity": 4},
                "liban_coach": {"confirmation_number": "LC-SEP02-77"},
                "maya": {"confirmation_number": "MH-SEP02"},
            },
        )
        arrange(
            tours["september"],
            lebanon,
            extras={
                "phoenicia": {
                    "confirmation_number": "PHX-SEP12-441",
                    "release_date": "2026-09-08",
                    "quantity": 10,
                    "notes": "Nadine Chami confirmed the 12 Sep block. Release remains 8 Sep.",
                },
                "liban_coach": {"confirmation_number": "LC-SEP12-204"},
                "maya": {"confirmation_number": "MH-SEP12"},
            },
        )
        arrange(
            tours["october"],
            lebanon,
            requested=("phoenicia",),
            extras={
                "phoenicia": {
                    "release_date": "2026-09-20",
                    "quantity": 8,
                    "notes": "Asked Nadine Chami for the 3 Oct block. Do not sell until she confirms.",
                }
            },
        )
        arrange(
            tours["petra_sep"],
            jordan,
            extras={
                "ishtar": {
                    "confirmation_number": "KHI-20991",
                    "release_date": "2026-09-06",
                    "quantity": 4,
                },
                "petra_trail": {"confirmation_number": "PTT-SEP20"},
            },
        )
        arrange(
            tours["petra_nov"],
            jordan,
            extras={
                "ishtar": {
                    "confirmation_number": "KHI-NOV-118",
                    "release_date": "2026-10-22",
                    "quantity": 2,
                    "notes": "Two twins held. Tania may drop — do not add extras yet.",
                }
            },
        )
        self.stdout.write("Supplier reservations seeded.")

    def _seed_expenses(self, catalog, tours) -> None:
        expenses = ExpenseService()
        pays = SupplierPaymentService()
        accountant = self.accountant_id
        owner = self.owner_id

        def tour_cost(*, tour, supplier, category, amount, description, date, due=None, pay=None, method=PaymentMethod.BANK_TRANSFER.value, reference=None):
            expense = expenses.create(
                actor_id=accountant,
                expense_scope=ExpenseScope.TOUR.value,
                category=category,
                amount=amount,
                description=description,
                expense_date=date,
                supplier_id=supplier["_id"],
                tour_id=tour["_id"],
                due_date=due,
            )
            if pay == "full":
                remaining = to_money(expense.get("remaining_amount") or amount)
                pays.create(
                    actor_id=accountant,
                    expense_id=expense["_id"],
                    amount=remaining,
                    payment_method=method,
                    payment_date=date,
                    reference_number=reference,
                )
            elif pay:
                pays.create(
                    actor_id=accountant,
                    expense_id=expense["_id"],
                    amount=pay,
                    payment_method=method,
                    payment_date=date,
                    reference_number=reference,
                )
            return expense

        tour_cost(
            tour=tours["august"],
            supplier=catalog["phoenicia"],
            category=ExpenseCategory.HOTEL.value,
            amount="5400.00",
            description="Phoenicia rooms, 8–14 Aug group",
            date="2026-07-20",
            due="2026-08-01",
            pay="full",
            reference="AUDI-PHX-AUG",
        )
        tour_cost(
            tour=tours["august"],
            supplier=catalog["liban_coach"],
            category=ExpenseCategory.TRANSPORTATION.value,
            amount="2400.00",
            description="Coach and driver, 8–14 Aug",
            date="2026-08-15",
            pay="full",
            method=PaymentMethod.BANK_TRANSFER.value,
            reference="BLOM-LC-AUG",
        )
        tour_cost(
            tour=tours["august"],
            supplier=catalog["maya"],
            category=ExpenseCategory.TOUR_GUIDE.value,
            amount="1050.00",
            description="Maya Haddad, 7 days August",
            date="2026-08-14",
            pay="full",
            method=PaymentMethod.CASH.value,
            reference="CASH-MAYA-AUG",
        )

        tour_cost(
            tour=tours["in_progress"],
            supplier=catalog["phoenicia"],
            category=ExpenseCategory.HOTEL.value,
            amount="4320.00",
            description="Phoenicia rooms, 2–8 Sep group on the road",
            date="2026-08-20",
            due="2026-09-01",
            pay="full",
            reference="AUDI-PHX-SEP02",
        )
        tour_cost(
            tour=tours["in_progress"],
            supplier=catalog["liban_coach"],
            category=ExpenseCategory.TRANSPORTATION.value,
            amount="2400.00",
            description="Coach, 2–8 Sep",
            date="2026-09-02",
            pay="1200.00",
            reference="BLOM-LC-SEP02-PART",
        )
        tour_cost(
            tour=tours["in_progress"],
            supplier=catalog["maya"],
            category=ExpenseCategory.TOUR_GUIDE.value,
            amount="1050.00",
            description="Guide fee, current Lebanon departure",
            date="2026-09-02",
            due="2026-09-08",
        )

        tour_cost(
            tour=tours["september"],
            supplier=catalog["phoenicia"],
            category=ExpenseCategory.HOTEL.value,
            amount="10800.00",
            description="Phoenicia estimated room block, 12–18 Sep",
            date="2026-09-01",
            due="2026-09-08",
        )
        tour_cost(
            tour=tours["september"],
            supplier=catalog["liban_coach"],
            category=ExpenseCategory.TRANSPORTATION.value,
            amount="2400.00",
            description="Coach reserved for 12–18 Sep",
            date="2026-09-01",
            due="2026-09-12",
            pay="full",
            reference="BLOM-LC-SEP12",
        )
        tour_cost(
            tour=tours["september"],
            supplier=catalog["jeita"],
            category=ExpenseCategory.ACTIVITY.value,
            amount="900.00",
            description="Jeita tickets and Byblos boat, 12–18 Sep",
            date="2026-09-04",
            due="2026-09-10",
        )

        tour_cost(
            tour=tours["petra_sep"],
            supplier=catalog["ishtar"],
            category=ExpenseCategory.HOTEL.value,
            amount="5800.00",
            description="Kempinski Ishtar, 20–25 Sep block",
            date="2026-08-25",
            due="2026-09-06",
            pay="2000.00",
            reference="ARB-KHI-DEP",
        )
        tour_cost(
            tour=tours["petra_sep"],
            supplier=catalog["petra_trail"],
            category=ExpenseCategory.TRANSPORTATION.value,
            amount="2650.00",
            description="Petra Trail circuit, 20–25 Sep",
            date="2026-09-01",
            due="2026-09-18",
        )

        expenses.create(
            actor_id=accountant,
            expense_scope=ExpenseScope.GENERAL.value,
            category=ExpenseCategory.RENT.value,
            amount="1800.00",
            description="Hamra office rent — September",
            expense_date="2026-09-01",
            due_date="2026-09-05",
        )
        marketing = expenses.create(
            actor_id=owner,
            expense_scope=ExpenseScope.GENERAL.value,
            category=ExpenseCategory.MARKETING.value,
            amount="450.00",
            description="Instagram ads, Lebanon autumn departures",
            expense_date="2026-08-28",
        )
        # Marketing has no supplier, so it stays unpaid on purpose unless we leave it as overhead.
        _ = marketing
        expenses.create(
            actor_id=accountant,
            expense_scope=ExpenseScope.GENERAL.value,
            category=ExpenseCategory.SOFTWARE.value,
            amount="89.00",
            description="Office 365 — September",
            expense_date="2026-09-01",
            due_date="2026-09-10",
        )
        self.stdout.write("Tour expenses, overhead, and supplier payments seeded.")
