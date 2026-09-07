from django.conf import settings
from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.accounts.repositories import UserRepository
from core.constants import UserStatus
from core.exceptions import DatabaseUnavailableError


class Command(BaseCommand):
    help = "Copy legacy Mongo staff users into Django auth, keeping the same actor ids."

    def handle(self, *args, **options):
        try:
            documents = UserRepository().list_users(include_deleted=True)
        except DatabaseUnavailableError as extra:
            self.stderr.write(self.style.ERROR(str(extra)))
            return

        imported = 0
        for document in documents:
            email = (document.get("email") or "").strip().lower()
            if not email:
                continue
            if User.objects.filter(email=email).exists():
                continue
            user = User(
                email=email,
                first_name=document.get("first_name") or "",
                last_name=document.get("last_name") or "",
                role=document.get("role") or "",
                phone=document.get("phone") or "",
                mongo_id=str(document["_id"]),
                is_active=document.get("status") == UserStatus.ACTIVE.value
                and not document.get("is_deleted"),
            )
            user.password = document.get("password_hash") or ""
            if not user.password:
                user.set_unusable_password()
            user.save()
            imported += 1
            self.stdout.write(self.style.SUCCESS(f"Imported {email}"))

        if imported == 0:
            self.stdout.write("No Mongo users needed importing.")
