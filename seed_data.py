# -*- coding: utf-8 -*-
import os
import sys
from pathlib import Path
from decimal import Decimal

# Setup Django Environment
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / 'apps'))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

def run_seed():
    print("========================================")
    print("🚀 Seeding TourOps Mock Data (English)...")
    print("========================================\n")

    # Import models safely
    Package = None
    Supplier = None

    try:
        from apps.packages.models import Package as PkgModel
        Package = PkgModel
    except Exception:
        try:
            from packages.models import Package as PkgModel
            Package = PkgModel
        except Exception as e:
            print(f"⚠️ Could not import Package model: {e}")

    try:
        from apps.suppliers.models import Supplier as SupModel
        Supplier = SupModel
    except Exception:
        try:
            from suppliers.models import Supplier as SupModel
            Supplier = SupModel
        except Exception:
            Supplier = None

    # 1. Seed Suppliers
    sup_turkey = None
    sup_egypt = None
    sup_alps = None
    sup_aegean = None

    if Supplier:
        sup_turkey, _ = Supplier.objects.get_or_create(
            name="Istanbul Tourism & Transfers",
            defaults={
                "contact_name": "Murat Yilmaz",
                "email": "murat@istanbultour.com",
                "phone": "+90 532 111 2233",
                "currency": "USD",
                "is_active": True
            }
        )
        sup_egypt, _ = Supplier.objects.get_or_create(
            name="Cairo Nile Voyages & Expeditions",
            defaults={
                "contact_name": "Tariq Mansour",
                "email": "tariq@nilevoyages.eg",
                "phone": "+20 100 555 4433",
                "currency": "USD",
                "is_active": True
            }
        )
        sup_alps, _ = Supplier.objects.get_or_create(
            name="Dolomites & Alps Alpine Guides",
            defaults={
                "contact_name": "Marco Rossi",
                "email": "marco@alpsadventures.it",
                "phone": "+39 0471 998877",
                "currency": "EUR",
                "is_active": True
            }
        )
        sup_aegean, _ = Supplier.objects.get_or_create(
            name="Aegean Luxury Charter & Ferries",
            defaults={
                "contact_name": "Eleni Papadopoulos",
                "email": "eleni@aegeancharter.gr",
                "phone": "+30 210 334 5566",
                "currency": "EUR",
                "is_active": True
            }
        )
        print("✓ Suppliers created successfully.")

    # 2. Seed Packages
    if Package:
        packages_data = [
            {
                "name": "Istanbul & Cappadocia Explorer",
                "code": "PKG-TR-2026",
                "duration_days": 7,
                "max_capacity": 25,
                "base_price": Decimal("1350.00"),
                "supplier": sup_turkey,
                "description": "A 7-day guided cultural tour covering Istanbul Old City, Bosphorus cruise, and Cappadocia hot air balloon flight.",
                "is_active": True,
            },
            {
                "name": "Cairo Discovery & Luxury Nile Cruise",
                "code": "PKG-EG-2026",
                "duration_days": 5,
                "max_capacity": 30,
                "base_price": Decimal("890.00"),
                "supplier": sup_egypt,
                "description": "A 5-day heritage trip covering the Pyramids of Giza, Grand Egyptian Museum, and Nile River cruise.",
                "is_active": True,
            },
            {
                "name": "Alpine Explorer 7D",
                "code": "PKG-ALP-001",
                "duration_days": 7,
                "max_capacity": 18,
                "base_price": Decimal("1850.00"),
                "supplier": sup_alps,
                "description": "Breathtaking hiking trails, cable car passes across Cortina d Ampezzo, and mountain lodge accommodations.",
                "is_active": True,
            },
            {
                "name": "Mediterranean Island Hopping",
                "code": "PKG-MED-002",
                "duration_days": 8,
                "max_capacity": 20,
                "base_price": Decimal("2100.00"),
                "supplier": sup_aegean,
                "description": "Private catamaran yacht sailing, coastal winery tastings, and boutique island resort stays across Santorini and Mykonos.",
                "is_active": True,
            },
            {
                "name": "Swiss Alps Winter Ski Escape",
                "code": "PKG-SKI-003",
                "duration_days": 6,
                "max_capacity": 15,
                "base_price": Decimal("2450.00"),
                "supplier": sup_alps,
                "description": "Unlimited 6-day ski lift passes in Zermatt, luxury chalet accommodation, and private ski instructor sessions.",
                "is_active": False,
            }
        ]

        pkg_field_names = {f.name for f in Package._meta.get_fields()}

        for p_data in packages_data:
            # Map fields dynamically to match your Package model
            filtered_kwargs = {}
            for k, v in p_data.items():
                if k in pkg_field_names:
                    if k == 'supplier' and v is None:
                        continue
                    filtered_kwargs[k] = v

            lookup_field = 'code' if 'code' in pkg_field_names else ('name' if 'name' in pkg_field_names else list(pkg_field_names)[0])
            lookup_val = p_data.get(lookup_field) or p_data['name']

            package, created = Package.objects.get_or_create(
                **{lookup_field: lookup_val},
                defaults=filtered_kwargs
            )
            status = "CREATED" if created else "EXISTS"
            print(f"  [Package: {status}] {package.name}")

    print("\n========================================")
    print("🎉 All Mock Data Loaded Successfully!")
    print("========================================")

if __name__ == '__main__':
    run_seed()