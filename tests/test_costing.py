from decimal import Decimal

from apps.packages.services import PackageService
from apps.suppliers.offerings import SupplierOfferingService
from apps.suppliers.services import SupplierService
from apps.tours.services import TourService
from core.constants import CostBasis, SupplierServiceKind, SupplierType
from core.costing import commercial_price, cost_sheet
from core.exceptions import ValidationError
from core.money import to_money


OWNER_ID = "000000000000000000000001"


def test_commercial_price_rounds_up_to_ten():
    assert commercial_price("1165.87") == Decimal("1170.00")
    assert commercial_price("100.00") == Decimal("100.00")
    assert commercial_price("0") == Decimal("0.00")


def test_land_cost_splits_person_and_group():
    sheet = cost_sheet(
        [
            {"name": "Hotel", "supplier_name": "Phoenicia", "estimated_cost": "540.00", "cost_basis": CostBasis.PER_PERSON.value, "service_kind": "ACCOMMODATION"},
            {"name": "Coach", "supplier": "Liban Coach", "estimated_cost": "1800.00", "cost_basis": CostBasis.PER_GROUP.value, "service_kind": "TRANSPORTATION"},
        ],
        capacity=18,
        selling_price="1250.00",
        margin_percent="30",
    )
    assert sheet["variable_per_person"] == Decimal("540.00")
    assert sheet["group_total"] == Decimal("1800.00")
    assert sheet["land_cost_per_person"] == Decimal("640.00")
    assert sheet["suggested_price"] == Decimal("920.00")
    assert sheet["profit_per_person"] == Decimal("610.00")
    assert sheet["below_cost"] is False
    assert sheet["break_even_pax"] == 3
    assert sheet["lines"][0]["supplier"] == "Phoenicia"
    assert sheet["lines"][1]["supplier"] == "Liban Coach"


def test_below_cost_when_price_under_land():
    sheet = cost_sheet(
        [{"name": "Hotel", "estimated_cost": "900.00", "cost_basis": "PER_PERSON"}],
        capacity=10,
        selling_price="800.00",
        margin_percent="30",
    )
    assert sheet["below_cost"] is True
    assert sheet["suggested_price"] == Decimal("1290.00")


def test_package_can_calculate_selling_price_from_costs():
    hotel = SupplierService().create(
        actor_id=OWNER_ID,
        name="Costed Hotel",
        supplier_type=SupplierType.HOTEL.value,
        city="Beirut",
        country="Lebanon",
    )
    stay = SupplierOfferingService().create(
        actor_id=OWNER_ID,
        supplier_id=hotel["_id"],
        name="Twin BB",
        service_kind=SupplierServiceKind.ACCOMMODATION.value,
        estimated_cost="1200.00",
        cost_basis=CostBasis.PER_PERSON.value,
    )
    package = PackageService().create(
        actor_id=OWNER_ID,
        name="Costed Lebanon",
        city="Beirut",
        country="Lebanon",
        duration_days=6,
        default_capacity=20,
        target_margin_percent="30",
        services=[{"supplier_service_id": stay["_id"]}],
    )
    assert to_money(package["selling_price_per_person"]) == Decimal("1720.00")
    presented = PackageService().get_presented(package["_id"])
    assert presented["costing"]["land_cost_per_person"] == Decimal("1200.00")
    assert presented["costing"]["suggested_price"] == Decimal("1720.00")
    assert presented["services"][0]["cost_basis"] == CostBasis.PER_PERSON.value
    assert presented["services"][0]["supplier"] == "Costed Hotel"
    assert presented["costing"]["lines"][0]["supplier"] == "Costed Hotel"


def test_package_without_costs_still_needs_a_price():
    try:
        PackageService().create(
            actor_id=OWNER_ID,
            name="Priceless",
            city="Beirut",
            duration_days=3,
            default_capacity=12,
        )
    except ValidationError as extra:
        assert "price" in extra.message.lower() or "cost" in extra.message.lower()
    else:
        raise AssertionError("expected ValidationError")


def test_tour_cost_sheet_uses_package_margin_and_capacity():
    hotel = SupplierService().create(
        actor_id=OWNER_ID,
        name="Sheet Hotel",
        supplier_type=SupplierType.HOTEL.value,
        city="Beirut",
        country="Lebanon",
    )
    stay = SupplierOfferingService().create(
        actor_id=OWNER_ID,
        supplier_id=hotel["_id"],
        name="Room share",
        service_kind=SupplierServiceKind.ACCOMMODATION.value,
        estimated_cost="500.00",
    )
    package = PackageService().create(
        actor_id=OWNER_ID,
        name="Sheet Package",
        city="Beirut",
        duration_days=5,
        selling_price_per_person="900.00",
        target_margin_percent="25",
        default_capacity=10,
        services=[{"supplier_service_id": stay["_id"]}],
    )
    tour = TourService().create(
        actor_id=OWNER_ID,
        package_id=package["_id"],
        start_date="2026-11-01",
        capacity=10,
    )
    presented = TourService().get_presented(tour["_id"])
    assert presented["price"] == Decimal("900.00")
    assert presented["costing"]["land_cost_per_person"] == Decimal("500.00")
    assert presented["costing"]["target_margin_percent"] == Decimal("25.00")
    assert presented["costing"]["suggested_price"] == Decimal("670.00")
