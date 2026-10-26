from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError


ROLES = ("Administrator", "Project Manager", "Annotator", "Reviewer", "Dataset Manager", "ML Engineer", "Read-only Auditor")


class Command(BaseCommand):
    help = "Assign an existing Django user to one of AURA's application roles."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("role", choices=ROLES)

    def handle(self, *args, **options):
        user_model = get_user_model()
        try:
            user = user_model.objects.get_by_natural_key(options["username"])
        except user_model.DoesNotExist as exc:
            raise CommandError(f"User '{options['username']}' does not exist. Create it with createsuperuser first.") from exc
        group, _ = Group.objects.get_or_create(name=options["role"])
        user.groups.add(group)
        self.stdout.write(self.style.SUCCESS(f"Assigned {options['role']} to {user.get_username()}."))
