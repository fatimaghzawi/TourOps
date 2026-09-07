from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from apps.customers.services import CustomerService
from apps.presentation.constants import SESSION_KEY, STORY
from apps.presentation.story import find_story, live_state
from apps.supplier_reservations.services import SupplierReservationService
from apps.tours.services import TourService
from core.constants import Collections, SupplierReservationStatus, SupplierType


def test_presentation_url_reverses():
    assert reverse("presentation:briefing") == "/presentation/"
    assert reverse("presentation:play") == "/presentation/watch/"
    assert reverse("presentation:jump", args=[3]) == "/presentation/go/3/"
    assert reverse("presentation:stop") == "/presentation/stop/"


def test_presentation_requires_login(client, settings):
    settings.DEBUG = True
    response = client.get(reverse("presentation:briefing"))
    assert response.status_code == 302
    assert reverse("accounts:login") in response["Location"]


def test_presentation_404_when_debug_off(owner_session, settings):
    settings.DEBUG = False
    response = owner_session.get(reverse("presentation:briefing"))
    assert response.status_code == 404


def test_briefing_without_seed_does_not_start(owner_session, settings):
    settings.DEBUG = True
    page = owner_session.get(reverse("presentation:briefing"))
    assert page.status_code == 200
    assert b"seed_istanbul_escape" in page.content
    started = owner_session.post(reverse("presentation:briefing"))
    assert started.status_code == 302
    assert started["Location"] == reverse("presentation:briefing")
    assert not owner_session.session.get(SESSION_KEY)


def test_product_pages_have_no_presentation_chrome(owner_session, settings):
    settings.DEBUG = True
    response = owner_session.get(reverse("dashboard:owner"))
    assert response.status_code == 200
    assert b"data-theater" not in response.content
    assert b"data-preso" not in response.content
    assert b"presentation/css/presentation.css" not in response.content


def test_slides_show_live_ui_step_by_step(owner_session, settings, fake_mongo):
    settings.DEBUG = True
    _insert_story(fake_mongo)
    page = owner_session.get(reverse("presentation:play") + "?s=1")
    assert page.status_code == 200
    assert b"<iframe" in page.content
    assert b"Agent" in page.content
    assert b"Edge case" not in page.content
    assert b"presentation.js" not in page.content
    assert b"maya.hassan@example.com" in page.content
    assert b'scrolling="no"' not in page.content

    suppliers = owner_session.get(reverse("presentation:play") + "?s=2")
    assert suppliers.status_code == 200
    assert b"hotel" in suppliers.content.lower()
    assert b"guide" in suppliers.content.lower()
    assert suppliers.content.count(b"<iframe") == 1

    invoices = owner_session.get(reverse("presentation:play") + "?s=12")
    assert invoices.status_code == 200
    assert b"invoice" in invoices.content.lower()
    assert b"Agent" in invoices.content

    refunds = owner_session.get(reverse("presentation:play") + "?s=13")
    assert refunds.status_code == 200
    assert b"refund" in refunds.content.lower()
    assert b"Agent" in refunds.content
    assert refunds.content.count(b"<iframe") == 2

    partial = owner_session.get(reverse("presentation:play") + "?s=15")
    assert partial.status_code == 200
    assert b"partial" in partial.content.lower()
    assert b"Accountant" in partial.content

    last = owner_session.get(reverse("presentation:play") + "?s=26")
    assert last.status_code == 200
    assert b"Owner" in last.content
    assert b"books" in last.content.lower()

    started = owner_session.post(reverse("presentation:briefing"), follow=False)
    assert started.status_code == 302
    assert reverse("presentation:play") in started["Location"]
    assert "s=1" in started["Location"]

    stopped = owner_session.get(reverse("presentation:stop"))
    assert stopped.status_code == 302
    assert stopped["Location"] == reverse("presentation:briefing")


def test_jump_lands_on_slide_query(owner_session, settings, fake_mongo):
    settings.DEBUG = True
    _insert_story(fake_mongo)
    stepped = owner_session.get(reverse("presentation:jump", args=[1]))
    assert stepped.status_code == 302
    assert reverse("presentation:play") in stepped["Location"]
    assert "s=2" in stepped["Location"]


def test_seed_istanbul_escape_refuses_when_debug_off(db, settings):
    settings.DEBUG = False
    try:
        call_command("seed_istanbul_escape")
    except CommandError as extra:
        assert "DEBUG" in str(extra)
    else:
        raise AssertionError("expected CommandError")


def test_seed_istanbul_escape_ready_for_live_run(db, settings):
    settings.DEBUG = True
    call_command("seed_istanbul_escape")
    story = find_story()
    assert story is not None
    assert story["tour_name"] == STORY["tour_name"]

    snapshot = live_state(story)
    assert snapshot["booked"] == 22
    assert snapshot["capacity"] == 30
    assert snapshot["confirmed"] == 0
    assert snapshot["planned"] == 3
    assert snapshot["can_take_bookings"] is False

    tour = TourService().get(story["tour_id"])
    assert tour["booked_seats"] == 22
    rows = SupplierReservationService().list_for_tour(story["tour_id"])
    assert {row["status"] for row in rows} == {SupplierReservationStatus.REQUESTED.value}

    maya = CustomerService().list_presented()
    names = {(row.get("first_name"), row.get("last_name")) for row in maya}
    assert (STORY["maya_first"], STORY["maya_last"]) not in names

    from apps.attachments.services import AttachmentService
    from apps.packages.services import PackageService
    from apps.suppliers.offerings import SupplierOfferingService
    from core.constants import AttachmentCategory, AttachmentEntityType

    photos = AttachmentService().list_for_entity(AttachmentEntityType.TOURS.value, story["tour_id"])
    gallery = [row for row in photos if row.get("category") == AttachmentCategory.GALLERY.value]
    assert len(gallery) == 4

    catalog = SupplierOfferingService().list_catalog()
    assert len(catalog) == 4
    assert all(row.get("supplier_id") and row.get("supplier") not in ("", "—") for row in catalog)

    package = PackageService().get_presented(story["package_id"])
    assert len(package.get("services") or []) == 4
    assert all(line.get("supplier_id") and line.get("supplier") not in ("", "—") for line in package["services"])

    tour = TourService().get_presented(story["tour_id"])
    assert len(tour.get("services") or []) == 4
    assert all(line.get("supplier_id") and line.get("supplier") not in ("", "—") for line in tour["services"])


def _insert_story(fake_mongo):
    hotel_id = fake_mongo.get_collection(Collections.SUPPLIERS).insert_one(
        {"name": STORY["hotel"], "supplier_type": SupplierType.HOTEL.value}
    ).inserted_id
    transport_id = fake_mongo.get_collection(Collections.SUPPLIERS).insert_one(
        {"name": STORY["transport"], "supplier_type": SupplierType.TRANSPORTATION.value}
    ).inserted_id
    fake_mongo.get_collection(Collections.SUPPLIERS).insert_one(
        {"name": STORY["guide"], "supplier_type": SupplierType.TOUR_GUIDE.value}
    )
    fake_mongo.get_collection(Collections.PACKAGES).insert_one({"name": STORY["package_name"]})
    tour_id = fake_mongo.get_collection(Collections.TOURS).insert_one(
        {"name": STORY["tour_name"], "capacity": 30, "booked_seats": 22}
    ).inserted_id
    fake_mongo.get_collection(Collections.SUPPLIER_RESERVATIONS).insert_one(
        {"tour_id": tour_id, "supplier_id": hotel_id, "status": "REQUESTED"}
    )
    fake_mongo.get_collection(Collections.SUPPLIER_RESERVATIONS).insert_one(
        {"tour_id": tour_id, "supplier_id": transport_id, "status": "REQUESTED"}
    )
    return tour_id
