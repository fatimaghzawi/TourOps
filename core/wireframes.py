from django.shortcuts import render

from apps.dashboard.mock_data import MOCK, get


def wireframe(request, template: str, title: str, heading: str | None = None, crumbs: list | None = None, **extra):
    context = {
        "page_title": title,
        "page_heading": heading or title,
        "crumbs": crumbs or [],
        "m": MOCK,
        **extra,
    }
    return render(request, template, context)


def record(kind: str, ident: str) -> dict:
    return get(kind, ident)


def crumbs(*pairs: tuple[str, str]) -> list[dict]:
    return [{"label": label, "url": url} for label, url in pairs]
