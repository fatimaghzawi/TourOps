from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from bson import ObjectId

from apps.attachments.services import AttachmentService
from apps.invoices.services import InvoiceService
from apps.payments.services import PaymentService
from apps.refunds.services import RefundService
from core.constants import AttachmentCategory, AttachmentEntityType, RefundPolicyTier, RefundStatus
from tests.test_business_flows import _booking, _customer, _expect_rule, _invoice, _pay, _tour
from tests.test_operations import OWNER_ID


def test_named_refund_tier_caps_amount():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    payment = _pay(invoice, "900.00")
    _expect_rule(
        lambda: RefundService().create_from_payment(
            payment["id"],
            reason="Too much for the window",
            refund_method="CASH",
            requested_by=OWNER_ID,
            amount="900.00",
            tier=RefundPolicyTier.DAYS_7_TO_14.value,
        ),
        "policy cap",
    )
    created = RefundService().create_from_payment(
        payment["id"],
        reason="Custom amount",
        refund_method="CASH",
        requested_by=OWNER_ID,
        amount="200.00",
        tier=RefundPolicyTier.OTHER.value,
    )
    assert created["amount"] == "200.00"


def test_cannot_void_payment_with_refund():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    payment = _pay(invoice, "400.00")
    RefundService().create_from_payment(
        payment["id"],
        reason="Pending payout",
        refund_method="CASH",
        requested_by=OWNER_ID,
        amount="100.00",
        tier=RefundPolicyTier.OTHER.value,
    )
    _expect_rule(lambda: PaymentService().void(payment["id"], actor_id=OWNER_ID), "refund")


def test_accountant_cannot_approve_refund_via_api(accountant_session):
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    payment = _pay(invoice, "400.00")
    refund = RefundService().create_from_payment(
        payment["id"],
        reason="Needs owner",
        refund_method="CASH",
        requested_by=OWNER_ID,
        amount="100.00",
        tier=RefundPolicyTier.OTHER.value,
    )
    response = accountant_session.post(reverse("refunds_api:approve", args=[refund["id"]]))
    assert response.status_code == 403
    assert RefundService().get(refund["id"])["status"] == RefundStatus.PENDING.value


def test_agent_cannot_see_expense_attachments(agent_session, accountant_session, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    created = AttachmentService().create(
        actor_id=OWNER_ID,
        entity_type=AttachmentEntityType.EXPENSES.value,
        entity_id=ObjectId(),
        category=AttachmentCategory.RECEIPT.value,
        upload=SimpleUploadedFile("receipt.png", b"\x89PNG\r\n\x1a\nhello", content_type="image/png"),
    )
    listing = agent_session.get(reverse("attachments:list"))
    assert listing.status_code == 200
    assert b"receipt.png" not in listing.content
    api = agent_session.get("/api/attachments/?entity_type=expenses")
    assert api.status_code == 200
    assert api.json()["data"]["attachments"] == []
    download = agent_session.get(reverse("attachments:download", args=[str(created["_id"])]))
    assert download.status_code != 200 or not download.get("Content-Disposition")
    denied = agent_session.get(f"/api/attachments/{created['_id']}/")
    assert denied.status_code == 403
    visible = accountant_session.get("/api/attachments/?entity_type=expenses")
    assert visible.json()["data"]["attachments"][0]["id"] == str(created["_id"])


def test_accountant_cannot_upload_tour_attachment(accountant_session, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    response = accountant_session.post(
        "/api/attachments/",
        {
            "entity_type": AttachmentEntityType.TOURS.value,
            "entity_id": str(ObjectId()),
            "category": AttachmentCategory.GALLERY.value,
            "upload": SimpleUploadedFile("photo.png", b"\x89PNG\r\n\x1a\nhello", content_type="image/png"),
        },
    )
    assert response.status_code == 403
    assert AttachmentService().list_presented() == []


def test_api_post_requires_csrf(owner_user):
    client = Client(enforce_csrf_checks=True)
    client.get(reverse("accounts:login"))
    client.force_login(owner_user)
    client.get(reverse("dashboard:home"), follow=True)
    payload = '{"first_name": "Nour", "last_name": "Haddad", "email": "nour-csrf@example.com"}'
    blocked = client.post("/api/customers/", data=payload, content_type="application/json")
    assert blocked.status_code == 403
    token = client.cookies["csrftoken"].value
    allowed = client.post(
        "/api/customers/",
        data=payload,
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert allowed.status_code == 201


def test_confirm_still_creates_invoice():
    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoices = InvoiceService().list_items(booking_id=str(booking["_id"]))
    assert len(invoices) == 1


def test_spoofed_png_upload_is_rejected(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    try:
        AttachmentService().create(
            actor_id=OWNER_ID,
            entity_type=AttachmentEntityType.EXPENSES.value,
            entity_id=ObjectId(),
            category=AttachmentCategory.RECEIPT.value,
            upload=SimpleUploadedFile("receipt.png", b"<html>not an image</html>", content_type="image/png"),
        )
    except Exception as extra:
        assert "contents" in str(extra).lower() or "supported" in str(extra).lower()
    else:
        raise AssertionError("expected rejected spoofed upload")


def test_create_user_api_does_not_return_password_hash(owner_session):
    response = owner_session.post(
        "/api/users/",
        data='{"first_name": "Nour", "last_name": "Haddad", "email": "nour-hash@example.com", "password": "changeme1", "role": "TRAVEL_AGENT"}',
        content_type="application/json",
    )
    assert response.status_code == 201
    payload = response.json()["data"]
    assert "password_hash" not in payload
    assert "password" not in payload


def test_second_live_invoice_is_blocked_by_unique_index(fake_mongo):
    from pymongo.errors import DuplicateKeyError

    tour = _tour()
    customer = _customer()
    booking = _booking(tour, customer, ["Fatima Ghazzawi"], confirm=True)
    invoice = _invoice(booking)
    try:
        fake_mongo.get_collection("invoices").insert_one(
            {
                "booking_id": booking["_id"],
                "invoice_number": "INV-DUP-1",
                "live_for_booking": True,
                "is_deleted": False,
                "status": "ISSUED",
            }
        )
    except DuplicateKeyError:
        pass
    else:
        raise AssertionError("expected unique live invoice per booking")
    assert InvoiceService().get(invoice["id"])["invoice_number"] == invoice["invoice_number"]
