import json
from decimal import Decimal

from bson import ObjectId
from django.urls import reverse

from apps.packages.services import PackageService
from apps.tours.services import TourService
from core.constants import PackageStatus, SupplierType
from core.exceptions import NotFoundError, ValidationError
from core.money import to_money


OWNER_ID = "000000000000000000000001"


def _create_package(**overrides):
    payload = {
        "actor_id": OWNER_ID,
        "name": "Istanbul Essentials",
        "city": "Istanbul",
        "country": "Turkey",
        "duration_days": 5,
        "selling_price_per_person": "699.00",
        "default_capacity": 16,
        "includes": "Hotel, Transfers, Guided tour",
        "excluded": "Flights, personal expenses",
        "description": "Classic Bosphorus week.",
    }
    payload.update(overrides)
    return PackageService().create(**payload)


def test_create_package_numbers_and_duration():
    package = _create_package()
    assert package["package_code"] == "PKG-1001"
    assert package["destination"]["city"] == "Istanbul"
    assert package["duration_days"] == 5
    assert to_money(package["selling_price_per_person"]) == Decimal("699.00")
    assert package["included_services"] == ["Hotel", "Transfers", "Guided tour"]
    presented = PackageService().get_presented(package["_id"])
    assert presented["duration"] == "5 days / 4 nights"
    assert presented["includes"] == "Hotel + Transfers + Guided tour"
    assert presented["code"] == "PKG-1001"


def test_create_requires_name_and_city():
    try:
        PackageService().create(actor_id=OWNER_ID, name="  ", city="Cairo", duration_days=3, selling_price_per_person="100")
    except ValidationError as extra:
        assert "name" in extra.message.lower()
    else:
        raise AssertionError("expected ValidationError")
    try:
        PackageService().create(actor_id=OWNER_ID, name="Cairo Heritage", duration_days=3, selling_price_per_person="100")
    except ValidationError as extra:
        assert "city" in extra.message.lower()
    else:
        raise AssertionError("expected ValidationError")


def test_cannot_delete_package_with_tours():
    package = _create_package()
    TourService().create(
        actor_id=OWNER_ID,
        package_id=package["_id"],
        start_date="2026-09-20",
    )
    try:
        PackageService().soft_delete(package["_id"], actor_id=OWNER_ID)
    except ValidationError as extra:
        assert "departures" in extra.message.lower()
    else:
        raise AssertionError("expected ValidationError")


def test_soft_delete_hides_package():
    package = _create_package()
    PackageService().soft_delete(package["_id"], actor_id=OWNER_ID)
    try:
        PackageService().get(package["_id"])
    except NotFoundError:
        pass
    else:
        raise AssertionError("expected NotFoundError")
    assert PackageService().list_items() == []


def test_agent_can_open_packages(agent_session):
    assert agent_session.get(reverse("packages:list")).status_code == 200
    assert agent_session.get(reverse("packages:create")).status_code == 200


def test_accountant_forbidden_from_packages(accountant_session):
    assert accountant_session.get(reverse("packages:list")).status_code == 403
    assert accountant_session.get("/api/packages/").status_code == 403


def test_html_create_and_detail(owner_session):
    response = owner_session.post(
        reverse("packages:create"),
        {
            "name": "Cairo Heritage",
            "city": "Cairo",
            "country": "Egypt",
            "duration_days": "6",
            "selling_price_per_person": "780.00",
            "currency": "USD",
            "default_capacity": "25",
            "included_services": "Hotel, Pyramids, Nile dinner",
            "excluded_services": "Domestic flights",
        },
    )
    assert response.status_code == 302, response.content
    package = PackageService().list_items()[0]
    assert package["package_code"] == "PKG-1001"
    detail = owner_session.get(reverse("packages:detail", args=[str(package["_id"])]))
    assert detail.status_code == 200
    assert b"PKG-1001" in detail.content
    assert b"Cairo Heritage" in detail.content
    listing = owner_session.get(reverse("packages:list"))
    assert b"Cairo Heritage" in listing.content


def test_html_unknown_id_redirects(owner_session):
    response = owner_session.get(reverse("packages:detail", args=["pkg-1001"]))
    assert response.status_code == 302
    assert reverse("packages:list") in response["Location"]


def test_html_empty_list(owner_session):
    response = owner_session.get(reverse("packages:list"))
    assert response.status_code == 200
    assert b"No packages yet" in response.content


def test_api_create_list_get_patch(owner_session):
    create = owner_session.post(
        "/api/packages/",
        data=json.dumps(
            {
                "name": "Dubai Escape",
                "city": "Dubai",
                "country": "UAE",
                "duration_days": 4,
                "price": 849,
                "default_capacity": 22,
                "includes": ["Hotel", "Desert safari"],
            }
        ),
        content_type="application/json",
    )
    assert create.status_code == 201, create.content
    body = create.json()
    assert body["success"] is True
    assert body["data"]["code"] == "PKG-1001"
    assert body["data"]["price"] == "849.00"
    assert body["data"]["duration"] == "4 days / 3 nights"
    package_id = body["data"]["id"]

    listing = owner_session.get("/api/packages/")
    assert listing.status_code == 200
    assert len(listing.json()["data"]["packages"]) == 1

    detail = owner_session.get(f"/api/packages/{package_id}/")
    assert detail.status_code == 200
    assert detail.json()["data"]["city"] == "Dubai"

    patch = owner_session.patch(
        f"/api/packages/{package_id}/",
        data=json.dumps({"status": PackageStatus.INACTIVE.value}),
        content_type="application/json",
    )
    assert patch.status_code == 200
    assert patch.json()["data"]["status"] == PackageStatus.INACTIVE.value
    assert patch.json()["data"]["city"] == "Dubai"


def test_api_unknown_id_is_404(owner_session):
    response = owner_session.get(f"/api/packages/{ObjectId()}/")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_api_rejects_invalid_json(owner_session):
    response = owner_session.post("/api/packages/", data="{", content_type="application/json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_package_services_require_supplier(fake_mongo):
    supplier = fake_mongo.get_collection("suppliers").insert_one(
        {
            "name": "Nile View Hotel",
            "supplier_type": SupplierType.HOTEL.value,
            "is_deleted": False,
        }
    )
    package = _create_package(
        services=[
            {
                "supplier_id": str(supplier.inserted_id),
                "description": "4-star hotel block",
                "estimated_cost": "1200.00",
            }
        ]
    )
    presented = PackageService().get_presented(package["_id"])
    assert presented["services"][0]["supplier"] == "Nile View Hotel"
    assert to_money(presented["services"][0]["est"]) == Decimal("1200.00")


def test_api_nested_tours_for_package(owner_session):
    package = _create_package()
    TourService().create(
        actor_id=OWNER_ID,
        package_id=package["_id"],
        name="Istanbul Week A",
        start_date="2026-09-12",
        end_date="2026-09-16",
    )
    response = owner_session.get(f"/api/packages/{package['_id']}/tours/")
    assert response.status_code == 200
    tours = response.json()["data"]["tours"]
    assert len(tours) == 1
    assert tours[0]["package_id"] == str(package["_id"])

    missing = owner_session.get(f"/api/packages/{ObjectId()}/tours/")
    assert missing.status_code == 404
