import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()

from apps.accounts.management.commands.seed_demo_user import ensure_demo_staff_quietly  # noqa: E402
from core.indexes import ensure_indexes_quietly  # noqa: E402

ensure_indexes_quietly()
ensure_demo_staff_quietly()
