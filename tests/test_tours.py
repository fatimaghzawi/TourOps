import json
from decimal import Decimal

from bson import ObjectId
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.attachments.services import AttachmentService
from apps.expenses.services import ExpenseService
from apps.notifications.constants import NotificationType
from apps.notifications.services import NotificationService
from apps.packages.services import PackageService
from apps.tours.schemas import available_seats
from apps.tours.services import TourService
from core.constants import ExpenseCategory, ExpenseScope, PackageStatus, TourStatus
from core.exceptions import NotFoundError, ValidationError
from core.money import to_money


OWNER_ID = "000000000000000000000001"


def _create_package(**overrides):
    payload = {
        "actor_id": OWNER_ID,
        "name": "Cairo Heritage",
        "city": "Cairo",
        "country": "Egypt",
        "duration_days": 5,
        "selling_price_per_person": "650.00",
        "default_capacity": 25,
        "includes": "Hotel, Pyramids",
    }
    payload.update(overrides)
    return PackageService().create(**payload)


def _create_tour(**overrides):
    payload = {
        "actor_id": OWNER_ID,
        "name": "Cairo Discovery",
        "city": "Cairo",
        "country": "Egypt",
        "start_date": "2026-09-12",
        "end_date": "2026-09-16",
        "capacity": 25,
        "selling_price_per_person": "650.00",
    }
    payload.update(overrides)
    if "package_id" not in payload:
        payload["package_id"] = _create_package()["_id"]
    return TourService().create(**payload)


def test_available_seats_never_negative():
    assert available_seats(25, 18) == 7
    assert available_seats(20, 20) == 0
    assert available_seats(10, 12) == 0


def test_create_tour_requires_package():
    try:
        TourService().create(
            actor_id=OWNER_ID,
            name="Orphan departure",
            city="Cairo",
            country="Egypt",
            start_date="2026-09-12",
            end_date="2026-09-16",
            capacity=10,
            selling_price_per_person="100.00",
        )
    except ValidationError as extra:
        assert "package" in extra.message.lower()
    else:
        raise AssertionError("expected ValidationError")


def test_cannot_create_tour_from_inactive_package():
    package = _create_package()
    PackageService().update(package["_id"], actor_id=OWNER_ID, status=PackageStatus.INACTIVE.value)
    try:
        TourService().create(actor_id=OWNER_ID, package_id=package["_id"], start_date="2026-10-01")
    except Exception as extra:
        assert "inactive" in str(extra).lower()
    else:
        raise AssertionError("expected inactive package rejection")


def test_create_tour_numbers_and_seats():
    tour = _create_tour()
    assert tour["tour_code"] == "TOUR-1001"
    assert tour["booked_seats"] == 0
    presented = TourService().get_presented(tour["_id"])
    assert presented["available"] == 25
    assert presented["pct"] == 0
    assert presented["dates"] == "12–16 Sep 2026"
    assert presented["status"] == TourStatus.AVAILABLE.value
    assert to_money(presented["price"]) == Decimal("650.00")


def test_create_from_package_copies_product_and_end_date():
    package = _create_package()
    tour = TourService().create(
        actor_id=OWNER_ID,
        package_id=package["_id"],
        start_date="2026-09-12",
    )
    assert tour["name"] == "Cairo Heritage"
    assert tour["destination"]["city"] == "Cairo"
    assert tour["capacity"] == 25
    assert to_money(tour["selling_price_per_person"]) == Decimal("650.00")
    assert tour["package_id"] == package["_id"]
    presented = TourService().get_presented(tour["_id"])
    assert presented["dates"] == "12–16 Sep 2026"
    assert presented["package"] == "Cairo Heritage"
    assert presented["included_services"] == ["Hotel", "Pyramids"]


def test_fully_booked_when_no_seats_left():
    tour = _create_tour(capacity=20, booked_seats=20)
    presented = TourService().get_presented(tour["_id"])
    assert presented["status"] == TourStatus.FULLY_BOOKED.value
    assert presented["available"] == 0
    assert presented["pct"] == 100


def test_cannot_lower_capacity_below_booked():
    tour = _create_tour(booked_seats=10, capacity=20)
    try:
        TourService().update(tour["_id"], capacity=8)
    except ValidationError as extra:
        assert "capacity" in extra.message.lower()
    else:
        raise AssertionError("expected ValidationError")


def test_cannot_delete_tour_with_bookings():
    tour = _create_tour(booked_seats=3)
    try:
        TourService().soft_delete(tour["_id"], actor_id=OWNER_ID)
    except ValidationError as extra:
        assert "booking" in extra.message.lower()
    else:
        raise AssertionError("expected ValidationError")


def test_soft_delete_hides_tour():
    tour = _create_tour()
    TourService().soft_delete(tour["_id"], actor_id=OWNER_ID)
    try:
        TourService().get(tour["_id"])
    except NotFoundError:
        pass
    else:
        raise AssertionError("expected NotFoundError")
    assert TourService().list_items() == []


def test_projected_profit_uses_expense_costs(fake_mongo):
    tour = _create_tour(booked_seats=10)
    ExpenseService().create(
        actor_id=OWNER_ID,
        expense_scope=ExpenseScope.TOUR.value,
        category=ExpenseCategory.MARKETING.value,
        amount="2000.00",
        description="Hotel block",
        expense_date="2026-09-12",
        tour_id=tour["_id"],
    )
    presented = TourService().get_presented(tour["_id"])
    assert to_money(presented["revenue"]) == Decimal("6500.00")
    assert to_money(presented["costs"]) == Decimal("2000.00")
    assert to_money(presented["profit"]) == Decimal("4500.00")
    assert presented["expenses"][0]["number"] == "EXP-1001"


def test_agent_can_open_tours(agent_session):
    assert agent_session.get(reverse("tours:list")).status_code == 200
    assert agent_session.get(reverse("tours:create")).status_code == 200
    assert agent_session.get(reverse("availability:index")).status_code == 200


def test_accountant_forbidden_from_tours(accountant_session):
    assert accountant_session.get(reverse("tours:list")).status_code == 403
    assert accountant_session.get("/api/tours/").status_code == 403


def test_html_create_detail_and_availability(owner_session):
    package = _create_package()
    response = owner_session.post(
        reverse("tours:create"),
        {
            "package_id": str(package["_id"]),
            "name": "Istanbul Explorer",
            "city": "Istanbul",
            "country": "Turkey",
            "start_date": "2026-09-15",
            "end_date": "2026-09-20",
            "capacity": "20",
            "selling_price_per_person": "890.00",
            "currency": "USD",
        },
    )
    assert response.status_code == 302, response.content
    tour = TourService().list_items()[0]
    assert tour["tour_code"] == "TOUR-1001"
    detail = owner_session.get(reverse("tours:detail", args=[str(tour["_id"])]))
    assert detail.status_code == 200
    assert b"TOUR-1001" in detail.content
    assert b"Istanbul Explorer" in detail.content
    listing = owner_session.get(reverse("tours:list"))
    assert b"Istanbul Explorer" in listing.content
    board = owner_session.get(reverse("availability:index"))
    assert board.status_code == 200
    assert b"Istanbul Explorer" in board.content
    assert b"20" in board.content


def test_html_tour_gallery_on_list_and_detail(owner_session, agent_session, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    package = _create_package()
    photo = SimpleUploadedFile("bosphorus.png", b"\x89PNG\r\n\x1a\nhello", content_type="image/png")
    created = owner_session.post(
        reverse("tours:create"),
        {
            "package_id": str(package["_id"]),
            "name": "Istanbul Explorer",
            "city": "Istanbul",
            "country": "Turkey",
            "start_date": "2026-09-15",
            "end_date": "2026-09-20",
            "capacity": "20",
            "selling_price_per_person": "890.00",
            "currency": "USD",
            "gallery": photo,
        },
    )
    assert created.status_code == 302, created.content
    tour = TourService().list_items()[0]
    listing = agent_session.get(reverse("tours:list"))
    assert listing.status_code == 200
    assert b"Istanbul Explorer" in listing.content
    assert b"t-hero has-photo" in listing.content
    assert b"/attachments/" in listing.content
    assert b"/preview/" in listing.content
    detail = agent_session.get(reverse("tours:detail", args=[str(tour["_id"])]) + "?tab=gallery")
    assert detail.status_code == 200
    assert b"data-gallery" in detail.content
    assert b"bosphorus.png" in detail.content
    photos = AttachmentService().gallery_for_tours([str(tour["_id"])]).get(str(tour["_id"]), [])
    assert photos
    preview = agent_session.get(reverse("attachments:preview", args=[photos[0]["id"]]))
    assert preview.status_code == 200
    form = owner_session.get(reverse("tours:create") + f"?package_id={package['_id']}")
    assert b"Client gallery" in form.content
    page = owner_session.get(reverse("tours:list"))
    assert b'id="app-confirm"' in page.content
    assert b"return confirm(" not in page.content


def test_html_tour_gallery_accepts_multiple_photos(owner_session, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    package = _create_package()
    png = b"\x89PNG\r\n\x1a\nhello"
    created = owner_session.post(
        reverse("tours:create"),
        {
            "package_id": str(package["_id"]),
            "name": "Istanbul Explorer",
            "city": "Istanbul",
            "country": "Turkey",
            "start_date": "2026-09-15",
            "end_date": "2026-09-20",
            "capacity": "20",
            "selling_price_per_person": "890.00",
            "currency": "USD",
            "gallery": [
                SimpleUploadedFile("bosphorus.png", png, content_type="image/png"),
                SimpleUploadedFile("blue-mosque.png", png, content_type="image/png"),
            ],
        },
    )
    assert created.status_code == 302, created.content
    tour = TourService().list_items()[0]
    photos = AttachmentService().gallery_for_tours([str(tour["_id"])]).get(str(tour["_id"]), [])
    assert len(photos) == 2
    extra = owner_session.post(
        reverse("tours:gallery_add", args=[str(tour["_id"])]),
        {
            "gallery": [
                SimpleUploadedFile("hagia-sophia.png", png, content_type="image/png"),
            ],
        },
    )
    assert extra.status_code == 302, extra.content
    photos = AttachmentService().gallery_for_tours([str(tour["_id"])]).get(str(tour["_id"]), [])
    assert len(photos) == 3
    gallery_tab = owner_session.get(reverse("tours:detail", args=[str(tour["_id"])]) + "?tab=gallery")
    assert gallery_tab.status_code == 200
    assert b"Upload photos" in gallery_tab.content
    assert b"multiple" in gallery_tab.content


def test_html_create_from_package(owner_session):
    package = _create_package()
    response = owner_session.post(
        reverse("tours:create"),
        {
            "package_id": str(package["_id"]),
            "start_date": "2026-09-12",
        },
    )
    assert response.status_code == 302, response.content
    tour = TourService().list_items()[0]
    assert tour["name"] == "Cairo Heritage"
    assert tour["capacity"] == 25
    assert tour["package_id"] == package["_id"]


def test_html_unknown_id_redirects(owner_session):
    response = owner_session.get(reverse("tours:detail", args=["tour-1001"]))
    assert response.status_code == 302
    assert reverse("tours:list") in response["Location"]


def test_html_empty_list(owner_session):
    response = owner_session.get(reverse("tours:list"))
    assert response.status_code == 200
    assert b"No tours yet" in response.content


def test_api_create_list_get_patch_availability(owner_session):
    package = _create_package()
    create = owner_session.post(
        "/api/tours/",
        data=json.dumps(
            {
                "package_id": str(package["_id"]),
                "name": "Cairo Discovery",
                "start_date": "2026-09-12",
                "end_date": "2026-09-16",
            }
        ),
        content_type="application/json",
    )
    assert create.status_code == 201, create.content
    body = create.json()
    assert body["success"] is True
    assert body["data"]["code"] == "TOUR-1001"
    assert body["data"]["available"] == 25
    assert body["data"]["price"] == "650.00"
    tour_id = body["data"]["id"]

    listing = owner_session.get("/api/tours/?package_id=" + str(package["_id"]))
    assert listing.status_code == 200
    assert len(listing.json()["data"]["tours"]) == 1

    detail = owner_session.get(f"/api/tours/{tour_id}/")
    assert detail.status_code == 200
    assert detail.json()["data"]["city"] == "Cairo"

    patch = owner_session.patch(
        f"/api/tours/{tour_id}/",
        data=json.dumps({"booked_seats": 18}),
        content_type="application/json",
    )
    assert patch.status_code == 200
    data = patch.json()["data"]
    assert data["booked"] == 18
    assert data["available"] == 7
    assert data["pct"] == 72

    seats = owner_session.get(f"/api/tours/{tour_id}/availability/")
    assert seats.status_code == 200
    assert seats.json()["data"]["available"] == 7
    assert seats.json()["data"]["booked"] == 18


def test_api_unknown_id_is_404(owner_session):
    response = owner_session.get(f"/api/tours/{ObjectId()}/")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_api_rejects_invalid_json(owner_session):
    response = owner_session.post("/api/tours/", data="{", content_type="application/json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
