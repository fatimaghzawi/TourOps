from apps.attachments.services import AttachmentService, present_attachment
from core.http import actor_id, actor_role, guarded, query_value, resource_id
from core.responses import success_response


def _upload(request):
    upload = request.FILES.get("file") or request.FILES.get("upload")
    return AttachmentService().create(
        actor_id=actor_id(request),
        actor_role=actor_role(request),
        entity_type=request.POST.get("entity_type") or "",
        entity_id=request.POST.get("entity_id") or "",
        category=request.POST.get("category") or "",
        upload=upload,
        notes=request.POST.get("notes"),
    )


@guarded
def list_attachments(request, **kwargs):
    items = AttachmentService().list_presented_for_role(
        actor_role(request),
        entity_type=query_value(request, "entity_type"),
        entity_id=query_value(request, "entity_id"),
        category=query_value(request, "category"),
    )
    return success_response({"attachments": items})


@guarded
def create_attachment(request, **kwargs):
    document = _upload(request)
    return success_response(present_attachment(document), status=201)


@guarded
def get_attachment(request, **kwargs):
    return success_response(AttachmentService().get_presented(resource_id(kwargs), actor_role=actor_role(request)))


@guarded
def download_attachment(request, **kwargs):
    return AttachmentService().file_response(resource_id(kwargs), actor_role=actor_role(request))


@guarded
def delete_attachment(request, **kwargs):
    AttachmentService().soft_delete(
        resource_id(kwargs),
        actor_id=actor_id(request),
        actor_role=actor_role(request),
    )
    return success_response({"deleted": True})
