from django.core.management.base import BaseCommand, CommandError

from aura_api import knowledge_service
from aura_api.config import MEDIA_DIR
from aura_api.models import KnowledgeSource


class Command(BaseCommand):
    help = "Rebuild a knowledge source index without displaying its content."

    def add_arguments(self, parser):
        parser.add_argument("--source-id", required=True)

    def handle(self, *args, **options):
        try:
            source = KnowledgeSource.objects.select_related("video").get(
                pk=options["source_id"], deleted_at__isnull=True,
            )
        except KnowledgeSource.DoesNotExist as exc:
            raise CommandError("Active knowledge source was not found.") from exc
        if source.source_type == "video":
            source = knowledge_service.index_video(source.video)
        else:
            media_root = MEDIA_DIR.resolve()
            path = (media_root / source.storage_key).resolve()
            if not source.storage_key or media_root not in path.parents or not path.is_file():
                raise CommandError("Private PDF source file is missing or outside the configured media root.")
            source = knowledge_service.ingest_pdf(source, path.read_bytes(), retry_count=source.jobs.count())
        self.stdout.write(self.style.SUCCESS(
            f"source={source.id} status={source.status} chunks={source.chunk_count} backend={source.index_backend}"
        ))
