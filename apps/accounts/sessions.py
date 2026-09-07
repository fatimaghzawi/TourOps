from django.contrib.sessions.models import Session


def revoke_user_sessions(user) -> int:
    """Drop every Django session belonging to this staff user."""
    if user is None or not getattr(user, "pk", None):
        return 0
    uid = str(user.pk)
    removed = 0
    for session in Session.objects.all():
        data = session.get_decoded()
        if str(data.get("_auth_user_id")) == uid:
            session.delete()
            removed += 1
    return removed
