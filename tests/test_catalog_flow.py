from decimal import Decimal

from django.urls import reverse

from apps.packages.services import PackageService
from apps.suppliers.offerings import SupplierOfferingService
from apps.suppliers.services import SupplierService
from apps.tours.services import TourService
from core.constants import PackageStatus, RecordStatus, SupplierServiceKind, SupplierType
from core.exceptions import NotFoundError, ValidationError
from core.money import to_money


OWNER_ID = "000000000000000000000001"


def _hotel(**overrides):
    payload = {
        "actor_id": OWNER_ID,
        "name": "Phoenicia Hotel",
        "supplier_type": SupplierType.HOTEL.value,
        "city": "Beirut",
        "country": "Lebanon",
        "star_rating": 5,
    }
    payload.update(overrides)
    return SupplierService().create(**payload)


def _offering(supplier, **overrides):
    payload = {
        "actor_id": OWNER_ID,
        "supplier_id": supplier["_id"],
        "name": "5-Night Accommodation",
        "service_kind": SupplierServiceKind.ACCOMMODATION.value,
        "estimated_cost": "1200.00",
    }
    payload.update(overrides)
    return SupplierOfferingService().create(**payload)


def _package_with_services(*offerings, **overrides):
    payload = {
        "actor_id": OWNER_ID,
        "name": "Lebanon Discovery",
        "city": "Beirut",
        "country": "Lebanon",
        "duration_days": 6,
        "selling_price_per_person": "1500.00",
        "default_capacity": 20,
        "services": [{"supplier_service_id": item["_id"]} for item in offerings],
    }
    payload.update(overrides)
    return PackageService().create(**payload)


def test_happy_path_supplier_service_package_tour_inherit():
    hotel = _hotel()
    stay = _offering(hotel)
    package = _package_with_services(stay)
    presented_package = PackageService().get_presented(package["_id"])
    assert presented_package["services"][0]["title"] == "5-Night Accommodation"
    assert presented_package["services"][0]["supplier"] == "Phoenicia Hotel"

    tour = TourService().create(actor_id=OWNER_ID, package_id=package["_id"], start_date="2026-10-10")
    presented = TourService().get_presented(tour["_id"])
    assert presented["package"] == "Lebanon Discovery"
    assert presented["name"] == "Lebanon Discovery"
    assert presented["dates"] == "10–15 Oct 2026"
    assert len(presented["services"]) == 1
    assert presented["services"][0]["title"] == "5-Night Accommodation"
    assert str(presented["services"][0]["supplier_service_id"]) == str(stay["_id"])
    assert to_money(presented["services"][0]["est"]) == Decimal("1200.00")


def test_catalog_change_does_not_rewrite_existing_tours_or_packages():
    hotel = _hotel()
    stay = _offering(hotel, estimated_cost="1200.00")
    package = _package_with_services(stay)
    tour = TourService().create(actor_id=OWNER_ID, package_id=package["_id"], start_date="2026-10-10")

    SupplierOfferingService().update(stay["_id"], actor_id=OWNER_ID, estimated_cost="1800.00", name="Deluxe 5-Night Stay")

    catalog = SupplierOfferingService().get(stay["_id"])
    assert catalog["name"] == "Deluxe 5-Night Stay"
    assert to_money(catalog["estimated_cost"]) == Decimal("1800.00")

    stored_package = PackageService().get(package["_id"])
    assert stored_package["services"][0]["name"] == "5-Night Accommodation"
    assert to_money(stored_package["services"][0]["estimated_cost"]) == Decimal("1200.00")

    stored_tour = TourService().get(tour["_id"])
    assert stored_tour["services"][0]["name"] == "5-Night Accommodation"
    assert to_money(stored_tour["services"][0]["estimated_cost"]) == Decimal("1200.00")


def test_duplicate_service_name_on_same_supplier_rejected():
    hotel = _hotel()
    _offering(hotel, name="Airport Transfer")
    try:
        _offering(hotel, name="airport transfer", service_kind=SupplierServiceKind.TRANSFER.value)
    except ValidationError as extra:
        assert "already has a service" in extra.message.lower()
    else:
        raise AssertionError("expected ValidationError")


def test_cannot_add_service_to_inactive_supplier():
    hotel = _hotel()
    SupplierService().update(hotel["_id"], actor_id=OWNER_ID, status=RecordStatus.INACTIVE.value)
    try:
        _offering(hotel)
    except ValidationError as extra:
        assert "inactive" in extra.message.lower()
    else:
        raise AssertionError("expected ValidationError")


def test_cannot_attach_inactive_service_to_new_package():
    hotel = _hotel()
    stay = _offering(hotel)
    SupplierOfferingService().set_status(stay["_id"], RecordStatus.INACTIVE.value, actor_id=OWNER_ID)
    try:
        _package_with_services(stay)
    except ValidationError as extra:
        assert "inactive" in extra.message.lower()
    else:
        raise AssertionError("expected ValidationError")


def test_cannot_delete_service_used_by_package():
    hotel = _hotel()
    stay = _offering(hotel)
    _package_with_services(stay)
    try:
        SupplierOfferingService().soft_delete(stay["_id"], actor_id=OWNER_ID)
    except ValidationError as extra:
        assert "deactivate" in extra.message.lower()
    else:
        raise AssertionError("expected ValidationError")


def test_cannot_delete_supplier_used_by_package():
    hotel = _hotel()
    stay = _offering(hotel)
    _package_with_services(stay)
    try:
        SupplierService().soft_delete(hotel["_id"], actor_id=OWNER_ID)
    except ValidationError as extra:
        assert "deactivate" in extra.message.lower()
    else:
        raise AssertionError("expected ValidationError")


def test_missing_supplier_cannot_own_a_service():
    try:
        SupplierOfferingService().create(
            actor_id=OWNER_ID,
            supplier_id="000000000000000000000099",
            name="Ghost service",
        )
    except NotFoundError:
        pass
    else:
        raise AssertionError("expected NotFoundError")


def test_tour_override_uses_existing_catalog_service_not_a_new_record():
    hotel = _hotel()
    stay = _offering(hotel)
    transfer = _offering(
        hotel,
        name="Airport Transfer",
        service_kind=SupplierServiceKind.TRANSFER.value,
        estimated_cost="80.00",
    )
    package = _package_with_services(stay)
    tour = TourService().create(
        actor_id=OWNER_ID,
        package_id=package["_id"],
        start_date="2026-11-05",
        service_ids=[str(transfer["_id"])],
    )
    presented = TourService().get_presented(tour["_id"])
    assert len(presented["services"]) == 1
    assert presented["services"][0]["title"] == "Airport Transfer"
    assert SupplierOfferingService().list_for_supplier(hotel["_id"]).__len__() == 2


def test_tour_override_rejects_inactive_catalog_service():
    hotel = _hotel()
    stay = _offering(hotel)
    other = _offering(hotel, name="Breakfast Package", service_kind=SupplierServiceKind.MEAL.value)
    SupplierOfferingService().set_status(other["_id"], RecordStatus.INACTIVE.value, actor_id=OWNER_ID)
    package = _package_with_services(stay)
    try:
        TourService().create(
            actor_id=OWNER_ID,
            package_id=package["_id"],
            start_date="2026-11-05",
            service_ids=[str(other["_id"])],
        )
    except ValidationError as extra:
        assert "inactive" in extra.message.lower()
    else:
        raise AssertionError("expected ValidationError")


def test_html_supplier_service_then_package_then_tour(owner_session):
    hotel = _hotel()
    create_page = owner_session.get(reverse("suppliers:service_create", args=[str(hotel["_id"])]))
    assert create_page.status_code == 200
    assert b"Add supplier service" in create_page.content

    posted = owner_session.post(
        reverse("suppliers:service_create", args=[str(hotel["_id"])]),
        {
            "name": "5-Night Accommodation",
            "service_kind": SupplierServiceKind.ACCOMMODATION.value,
            "estimated_cost": "1200.00",
            "currency": "USD",
        },
    )
    assert posted.status_code == 302, posted.content
    offering = SupplierOfferingService().list_for_supplier(hotel["_id"])[0]
    assert offering["name"] == "5-Night Accommodation"

    detail = owner_session.get(reverse("suppliers:detail", args=[str(hotel["_id"])]) + "?tab=services")
    assert detail.status_code == 200
    assert b"5-Night Accommodation" in detail.content

    package_page = owner_session.get(reverse("packages:create"))
    assert package_page.status_code == 200
    assert b"Phoenicia Hotel" in package_page.content
    assert b"5-Night Accommodation" in package_page.content

    created_package = owner_session.post(
        reverse("packages:create"),
        {
            "name": "Lebanon Discovery",
            "city": "Beirut",
            "country": "Lebanon",
            "duration_days": "6",
            "selling_price_per_person": "1500.00",
            "currency": "USD",
            "default_capacity": "20",
            "service_ids": [offering["id"]],
        },
    )
    assert created_package.status_code == 302, created_package.content
    package = PackageService().list_items()[0]
    assert package["name"] == "Lebanon Discovery"
    assert len(package["services"]) == 1

    blank_tour = owner_session.get(reverse("tours:create"))
    assert blank_tour.status_code == 200

    tour_page = owner_session.get(reverse("tours:create") + f"?package_id={package['_id']}")
    assert tour_page.status_code == 200
    assert b"Lebanon Discovery" in tour_page.content
    assert b"5-Night Accommodation" in tour_page.content
    assert b"Replace inherited services" in tour_page.content

    created_tour = owner_session.post(
        reverse("tours:create"),
        {
            "package_id": str(package["_id"]),
            "start_date": "2026-10-10",
        },
    )
    assert created_tour.status_code == 302, created_tour.content
    tour = TourService().list_items()[0]
    assert tour["package_id"] == package["_id"]
    assert tour["services"][0]["name"] == "5-Night Accommodation"


def test_html_tour_create_without_package_shows_empty_state(owner_session):
    page = owner_session.get(reverse("tours:create"))
    assert page.status_code == 200
    assert b"Create a package first" in page.content


def test_html_inactive_package_cannot_spawn_tour_button(owner_session):
    package = PackageService().create(
        actor_id=OWNER_ID,
        name="Archived product",
        city="Beirut",
        country="Lebanon",
        duration_days=5,
        selling_price_per_person="900.00",
        default_capacity=12,
        status=PackageStatus.INACTIVE.value,
    )
    detail = owner_session.get(reverse("packages:detail", args=[str(package["_id"])]))
    assert detail.status_code == 200
    assert b"disabled" in detail.content
    assert b"Create tour" in detail.content


def test_accountant_cannot_add_supplier_service(accountant_session):
    hotel = _hotel()
    response = accountant_session.get(reverse("suppliers:service_create", args=[str(hotel["_id"])]))
    assert response.status_code == 403
    catalog = accountant_session.get("/api/suppliers/services/")
    assert catalog.status_code == 403
    page = accountant_session.get(reverse("suppliers:services"))
    assert page.status_code == 403


def test_dashboard_links_to_add_services(owner_session):
    agent = owner_session.get(reverse("dashboard:agent"))
    assert agent.status_code == 200
    assert b"Add services" in agent.content
    assert reverse("suppliers:service_new").encode() in agent.content
    assert b"On an existing supplier" in agent.content
    owner = owner_session.get(reverse("dashboard:owner"))
    assert owner.status_code == 200
    assert b"Jump to" not in owner.content


def test_add_service_for_existing_supplier(owner_session):
    hotel = _hotel()
    page = owner_session.get(reverse("suppliers:service_new"))
    assert page.status_code == 200
    assert b"Existing supplier" in page.content
    assert b"Phoenicia Hotel" in page.content
    assert b"Create supplier" in page.content
    assert b'data-supplier-row' in page.content
    assert b'data-supplier-filter' in page.content
    assert str(hotel["_id"]).encode() in page.content
    posted = owner_session.post(
        reverse("suppliers:service_new"),
        {
            "supplier_id": str(hotel["_id"]),
            "name": "Breakfast Package",
            "service_kind": SupplierServiceKind.MEAL.value,
            "estimated_cost": "40.00",
            "currency": "USD",
        },
    )
    assert posted.status_code == 302, posted.content
    rows = SupplierOfferingService().list_for_supplier(hotel["_id"])
    assert [row["name"] for row in rows] == ["Breakfast Package"]


def test_catalog_page_adds_service_via_supplier_picker(owner_session):
    hotel = _hotel()
    page = owner_session.get(reverse("suppliers:services"))
    assert page.status_code == 200
    assert b"Add service for existing supplier" in page.content
    picked = owner_session.get(reverse("suppliers:services") + f"?supplier_id={hotel['_id']}")
    assert picked.status_code == 302
    assert reverse("suppliers:service_create", args=[str(hotel["_id"])]) in picked["Location"]
    listing = owner_session.get(reverse("suppliers:list"))
    assert b"Add service" in listing.content
    standalone = owner_session.get(reverse("suppliers:service_new") + f"?supplier_id={hotel['_id']}")
    assert standalone.status_code == 200
    assert b"Phoenicia Hotel" in standalone.content
