from django.urls import reverse


def test_wireframe_pages_render(owner_session):
    named = [
        ("dashboard:owner", None),
        ("dashboard:agent", None),
        ("customers:list", None),
        ("customers:create", None),
        ("bookings:list", None),
        ("bookings:create", None),
        ("supplier_reservations:list", None),
        ("supplier_reservations:create", None),
        ("tours:list", None),
        ("tours:create", None),
        ("availability:index", None),
        ("packages:list", None),
        ("packages:create", None),
        ("suppliers:list", None),
        ("suppliers:services", None),
        ("suppliers:service_new", None),
        ("suppliers:hotels", None),
        ("suppliers:create", None),
        ("invoices:list", None),
        ("invoices:create", None),
        ("payments:list", None),
        ("payments:create", None),
        ("receipts:list", None),
        ("refunds:list", None),
        ("refunds:create", None),
        ("expenses:list", None),
        ("expenses:create", None),
        ("supplier_payments:list", None),
        ("supplier_payments:create", None),
        ("finance:customer_balances", None),
        ("finance:supplier_balances", None),
        ("finance:receivables", None),
        ("finance:payables", None),
        ("reports:list", None),
        ("reports:profitability", None),
        ("reports:revenue", None),
        ("reports:expenses", None),
        ("reports:profit_loss", None),
        ("reports:payments", None),
        ("reports:refunds", None),
        ("reports:transactions", None),
        ("dashboard:accountant", None),
        ("notifications:list", None),
        ("attachments:list", None),
        ("audit:list", None),
        ("accounts:users", None),
        ("accounts:user_create", None),
        ("accounts:settings", None),
    ]
    for name, args in named:
        url = reverse(name, args=args) if args else reverse(name)
        response = owner_session.get(url)
        assert response.status_code == 200, f"{name} {url} -> {response.status_code}"


def test_missing_finance_records_are_not_found(owner_session):
    named = [
        ("invoices:detail", ["inv-1042"]),
        ("invoices:print", ["inv-1042"]),
        ("payments:detail", ["pay-1042"]),
        ("receipts:detail", ["rec-1042"]),
        ("refunds:detail", ["ref-1012"]),
    ]
    for name, args in named:
        url = reverse(name, args=args)
        response = owner_session.get(url)
        assert response.status_code == 404, f"{name} {url} -> {response.status_code}"
