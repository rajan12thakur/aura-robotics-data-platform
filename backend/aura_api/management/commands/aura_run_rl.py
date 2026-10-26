import json

from django.core.management.base import BaseCommand, CommandError

from aura_api.models import AuditEvent, Project
from aura_api.rl_service import execute_experiment


class Command(BaseCommand):
    help = "Run a bounded task-level Q-learning or baseline experiment and persist its results."

    def add_arguments(self, parser):
        parser.add_argument("--project-id", required=True)
        parser.add_argument("--algorithm", choices=("q_learning", "baseline"), default="q_learning")
        parser.add_argument("--episodes", type=int, default=500)
        parser.add_argument("--seed", type=int, default=7)
        parser.add_argument("--max-steps", type=int, default=40)

    def handle(self, *args, **options):
        try:
            project = Project.objects.get(pk=options["project_id"])
        except Project.DoesNotExist as exc:
            raise CommandError("Project does not exist.") from exc
        try:
            run, result = execute_experiment(
                project=project,
                actor="management-command",
                algorithm=options["algorithm"],
                episodes=options["episodes"],
                seed=options["seed"],
                max_steps=options["max_steps"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        AuditEvent.objects.create(
            project=project,
            event_type="rl.experiment.succeeded",
            actor="management-command",
            summary=f"Completed {run.algorithm} experiment with {result['configuration']['episodes']} training episode(s).",
            details_json=json.dumps({
                "experiment_id": run.id,
                "seed": run.random_seed,
                "evaluation": result["metrics"]["evaluation"],
            }),
        )
        self.stdout.write(self.style.SUCCESS(
            f"Experiment {run.id} succeeded: learned policy success "
            f"{result['metrics']['evaluation']['learned_policy']['success_rate']:.0%}; "
            f"baseline success {result['metrics']['evaluation']['baseline_policy']['success_rate']:.0%}."
        ))
