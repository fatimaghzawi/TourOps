from django import template

register = template.Library()

_BADGE = {
    "ACTIVE": "b-ok",
    "AVAILABLE": "b-ok",
    "REQUESTED": "b-warn",
    "CONFIRMED": "b-ok",
    "COMPLETED": "b-ok",
    "PAID": "b-ok",
    "APPROVED": "b-ok",
    "PENDING": "b-warn",
    "DRAFT": "b-mute",
    "ISSUED": "b-info",
    "PARTIALLY_PAID": "b-warn",
    "PARTIALLY_REFUNDED": "b-info",
    "REFUNDED": "b-info",
    "UNPAID": "b-bad",
    "IN_PROGRESS": "b-info",
    "FULLY_BOOKED": "b-warm",
    "INACTIVE": "b-mute",
    "CANCELLED": "b-bad",
    "REJECTED": "b-bad",
    "VOIDED": "b-bad",
    "OVERDUE": "b-bad",
    "REFUNDED": "b-info",
    "HOTEL": "b-warm",
    "TRANSPORTATION": "b-info",
    "TOUR_GUIDE": "b-ok",
    "AIRLINE": "b-info",
    "ACTIVITY_PROVIDER": "b-warm",
    "RESTAURANT": "b-ok",
    "INSURANCE": "b-mute",
    "OTHER": "b-mute",
    "OWNER_ADMIN": "b-warm",
    "ACCOUNTANT": "b-info",
    "TRAVEL_AGENT": "b-ok",
    "SHORTAGE": "b-bad",
    "UNUSED": "b-info",
    "OK": "b-ok",
    "CAPACITY OK": "b-ok",
    "UNUSED CAPACITY": "b-info",
    "NONE": "b-mute",
}


@register.filter
def money(value):
    if value is None or value == "":
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return f"${number:,.0f}"
    return f"${number:,.2f}"


@register.filter
def money_signed(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    sign = "+" if number >= 0 else "−"
    return f"{sign}{money(abs(number))}"


@register.filter
def add_money(left, right):
    try:
        return float(left or 0) + float(right or 0)
    except (TypeError, ValueError):
        return 0


@register.filter
def width_pct(part, whole):
    try:
        amount = abs(float(part or 0))
        total = abs(float(whole or 0))
    except (TypeError, ValueError):
        return 0
    if total <= 0:
        return 0
    return int(max(0, min(100, round(amount / total * 100))))


@register.filter
def badge_class(status):
    return _BADGE.get(str(status or "").upper(), "b-mute")


@register.filter
def labelize(value):
    return str(value or "").replace("_", " ").title()


@register.simple_tag(takes_context=True)
def nav_active(context, *namespaces):
    match = getattr(context.get("request"), "resolver_match", None)
    current = getattr(match, "namespace", "")
    return "is-active" if current in namespaces else ""
