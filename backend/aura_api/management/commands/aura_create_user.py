from getpass import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create a non-superuser AURA account with a hidden password prompt."

    def add_arguments(self, parser):
        parser.add_argument("username")

    def handle(self, *args, **options):
        username = options["username"].strip()
        user_model = get_user_model()
        if not username or len(username) > 150:
            raise CommandError("Username must contain 1 to 150 characters.")
        if user_model.objects.filter(**{f"{user_model.USERNAME_FIELD}__iexact": username}).exists():
            raise CommandError(f"User '{username}' already exists.")
        password = getpass("Password: ")
        confirmation = getpass("Confirm password: ")
        if not password or password != confirmation:
            raise CommandError("Passwords must be non-empty and match.")
        username_field = user_model.USERNAME_FIELD
        candidate = user_model(**{username_field: username})
        try:
            validate_password(password, candidate)
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages)) from exc
        user = user_model.objects.create_user(**{username_field: username, "password": password})
        self.stdout.write(self.style.SUCCESS(f"Created local AURA account '{user.get_username()}'. Assign a role with aura_assign_role."))
