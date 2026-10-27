import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from aura_rag.evaluation import evaluate_retrieval_fixture, lexical_fixture_retriever


class Command(BaseCommand):
    help = "Evaluate lexical retrieval against the bundled synthetic evidence fixture."

    def add_arguments(self, parser):
        parser.add_argument("--top-k", type=int, default=3)

    def handle(self, *args, **options):
        top_k = options["top_k"]
        if top_k < 1 or top_k > 20:
            raise CommandError("--top-k must be between 1 and 20.")
        fixture_path = Path(__file__).resolve().parents[4] / "data" / "examples" / "rag_retrieval_evaluation.json"
        try:
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError("Could not load the synthetic retrieval evaluation fixture.") from exc
        metrics = evaluate_retrieval_fixture(fixture, lexical_fixture_retriever, top_k)
        self.stdout.write(json.dumps({
            "fixture_label": fixture["fixture_label"],
            "retrieval_mode": "lexical_sqlite scoring function; offline fixture evaluation",
            "metrics": metrics,
        }, indent=2))
