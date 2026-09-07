import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()

from core.indexes import ensure_indexes_quietly  # noqa: E402

ensure_indexes_quietly()
