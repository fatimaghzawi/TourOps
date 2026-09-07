from __future__ import annotations

import logging
import sys

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import IntegrityError

from apps.accounts.models import User
from core.constants import UserRole


STAFF = (
    (settings.DEMO_OWNER_EMAIL, settings.DEMO_OWNER_PASSWORD, "Rami", "Khoury", UserRole.OWNER_ADMIN),
    (settings.DEMO_AGENT_EMAIL, settings.DEMO_AGENT_PASSWORD, "Amina", "Haddad", UserRole.TRAVEL_AGENT),
    (settings.DEMO_ACCOUNTANT_EMAIL, settings.DEMO_ACCOUNTANT_PASSWORD, "Karim", "Nassar", UserRole.ACCOUNTANT),
)


def ensure_demo_staff_quietly() -> None:
    if "pytest" in sys.modules:
        return
    try:
        from django.core.management import call_command

        call_command("seed_demo_user")
    except Exception:
        logging.getLogger(__name__).exception("Could not seed demo staff.")


class Command(BaseCommand):
    help = "Seed demo staff users (owner, agent, accountant) into Django auth."

    def handle(self, *args, **options):
        bootstrap = not User.objects.exists()
        if not settings.DEBUG and not settings.SEED_DEMO_USER and not bootstrap:
            self.stdout.write("Skipping demo staff seed (DEBUG is False).")
            return

        reset_passwords = bool(settings.SEED_DEMO_USER)
        created = 0
        for email, password, first_name, last_name, role in STAFF:
            email = email.strip().lower()
            existing = User.objects.filter(email=email).first()
            if existing:
                changed = False
                if existing.first_name != first_name:
                    existing.first_name = first_name
                    changed = True
                if existing.last_name != last_name:
                    existing.last_name = last_name
                    changed = True
                if existing.role != role.value:
                    existing.role = role.value
                    changed = True
                if not existing.is_active:
                    existing.is_active = True
                    changed = True
                if reset_passwords:
                    existing.set_password(password)
                    changed = True
                if changed:
                    existing.save()
                    self.stdout.write(self.style.SUCCESS(f"Updated {email} ({first_name} {last_name})"))
                else:
                    self.stdout.write(self.style.WARNING(f"User already exists: {email}"))
                continue
            try:
                User.objects.create_user(
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    role=role.value,
                    is_active=True,
                )
            except IntegrityError:
                self.stdout.write(self.style.WARNING(f"User already exists: {email}"))
                continue
            created += 1
            self.stdout.write(self.style.SUCCESS(f"Created {email} / {password} ({role.value})"))

        if created:
            self.stdout.write("Change these passwords before sharing the environment.")
