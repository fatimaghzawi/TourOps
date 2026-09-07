from django.core.management.base import BaseCommand

from core.exceptions import DatabaseUnavailableError
from core.indexes import ensure_indexes


class Command(BaseCommand):
    help = "Create recommended MongoDB indexes (unique business numbers, emails, ...)."

    def handle(self, *args, **options):
        try:
            created = ensure_indexes()
        except DatabaseUnavailableError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return
        for line in created:
            self.stdout.write(f"  {line}")
        self.stdout.write(self.style.SUCCESS("Indexes ensured."))
