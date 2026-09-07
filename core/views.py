from django.shortcuts import render


def placeholder_page(
    request,
    *,
    title: str,
    module: str,
    owner: str,
    description: str,
    extra_context: dict | None = None,
):
    context = {
        "page_title": title,
        "module_name": module,
        "module_owner": owner,
        "module_description": description,
        "page_heading": title,
    }
    if extra_context:
        context.update(extra_context)
    return render(request, "placeholder.html", context)


def handler403(request, exception=None):
    return render(request, "errors/403.html", {"page_title": "Forbidden", "page_heading": "Forbidden"}, status=403)


def handler404(request, exception=None):
    return render(request, "errors/404.html", {"page_title": "Not found", "page_heading": "Not found"}, status=404)


def handler500(request):
    return render(request, "errors/500.html", {"page_title": "Server error", "page_heading": "Server error"}, status=500)
