from django.conf import settings
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods

from apps.presentation.constants import SESSION_KEY, STAGES
from apps.presentation.scenes import first_scene_for_stage, scenes_for, stage_index
from apps.presentation.story import demo_cast, find_story, live_state
from core.exceptions import DatabaseUnavailableError, TourOpsError
from core.permissions import login_required


def _require_debug():
    if not settings.DEBUG:
        raise Http404("Presentation mode is only available when DEBUG is on.")


def _story_or_message():
    try:
        story = find_story()
    except DatabaseUnavailableError:
        return None, "Cannot reach MongoDB. Presentation data is unavailable."
    if not story:
        return None, "Istanbul Escape is not seeded. Run python manage.py seed_istanbul_escape"
    return story, None


def _slide_number(request, total: int) -> int:
    try:
        slide = int(request.GET.get("s") or 1)
    except (TypeError, ValueError):
        slide = 1
    if total < 1:
        return 1
    return max(1, min(slide, total))


def _slide_context(request):
    story, error = _story_or_message()
    scenes = scenes_for(story or {})
    total = len(scenes)
    slide = _slide_number(request, total)
    scene = scenes[slide - 1] if scenes else {}
    current_stage = stage_index(scene.get("stage") or "supplier")
    steps = []
    for offset, (key, label) in enumerate(STAGES):
        start = first_scene_for_stage(key)
        if offset < current_stage:
            state = "done"
        elif offset == current_stage:
            state = "now"
        else:
            state = "todo"
        steps.append({"key": key, "label": label, "slide": start + 1, "state": state})
    return {
        "error": error,
        "scene": scene,
        "slide": slide,
        "total": total,
        "prev": slide - 1 if slide > 1 else None,
        "next": slide + 1 if slide < total else None,
        "steps": steps,
        "panes": scene.get("panes") or [{"path": "/", "label": ""}],
        "role": scene.get("role") or "Agent",
        "layout": scene.get("layout") or "one",
        "cast": demo_cast(story),
    }


@login_required
@require_http_methods(["GET", "POST"])
def briefing(request):
    _require_debug()
    story, error = _story_or_message()
    if request.method == "POST":
        if error:
            return redirect("presentation:briefing")
        request.session[SESSION_KEY] = {"active": True, "scene": 0, "story": story}
        request.session.modified = True
        return HttpResponseRedirect(reverse("presentation:play") + "?s=1")
    if error:
        return render(request, "presentation/slide.html", _slide_context(request))
    return HttpResponseRedirect(reverse("presentation:play") + "?s=1")


@login_required
@require_GET
def play(request):
    _require_debug()
    return render(request, "presentation/slide.html", _slide_context(request))


@login_required
@require_http_methods(["GET", "POST"])
def stop(request):
    _require_debug()
    request.session.pop(SESSION_KEY, None)
    request.session.modified = True
    return redirect("presentation:briefing")


@login_required
@require_GET
def jump(request, index: int):
    _require_debug()
    scenes = scenes_for()
    if not scenes:
        return redirect("presentation:play")
    slide = max(1, min(int(index) + 1, len(scenes)))
    return HttpResponseRedirect(reverse("presentation:play") + f"?s={slide}")


@login_required
def state(request):
    _require_debug()
    story, _error = _story_or_message()
    if not story:
        return JsonResponse({"active": False})
    try:
        snapshot = live_state(story)
    except TourOpsError as extra:
        return JsonResponse({"active": True, "error": extra.message}, status=400)
    except Exception:
        return JsonResponse({"active": True, "error": "Story data is unavailable."}, status=400)
    return JsonResponse({"active": True, **snapshot})
