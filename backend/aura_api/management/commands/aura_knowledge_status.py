from django.core.management.base import BaseCommand

from aura_api.models import KnowledgeJob, KnowledgeSource


class Command(BaseCommand):
    help = "Show knowledge-source and indexing status without printing document text."

    def handle(self, *args, **options):
        sources = KnowledgeSource.objects.filter(deleted_at__isnull=True).order_by("project_id", "created_at")
        self.stdout.write("project_id\tsource_id\ttype\tstatus\tchunks\tbackend\tsha256")
        for source in sources.iterator():
            self.stdout.write(
                f"{source.project_id}\t{source.id}\t{source.source_type}\t{source.status}\t"
                f"{source.chunk_count}\t{source.index_backend}\t{source.checksum_sha256}"
            )
        self.stdout.write(
            f"active_sources={sources.count()} active_jobs={KnowledgeJob.objects.filter(status__in=['queued', 'processing']).count()} "
            f"failed_jobs={KnowledgeJob.objects.filter(status='failed').count()}"
        )
