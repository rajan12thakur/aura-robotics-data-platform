import json

from django.core.management.base import BaseCommand, CommandError

from aura_api.data_pipeline import run_pipeline
from aura_api.models import Project


class Command(BaseCommand):
    help = "Build idempotent Bronze/Silver/Gold artifacts from a project's AURA records."

    def add_arguments(self, parser):
        parser.add_argument("--project-id", required=True)

    def handle(self, *args, **options):
        project_id = options["project_id"]
        if not Project.objects.filter(pk=project_id).exists():
            raise CommandError("The requested project does not exist.")
        result = run_pipeline(project_id)
        self.stdout.write(json.dumps(result, indent=2, sort_keys=True))
