"""Persisted local-runner lifecycle for bounded reinforcement-learning experiments."""

import json
import logging

from django.utils import timezone

from .models import AuditEvent, RLExperiment
from .rl import ENVIRONMENT_VERSION, run_experiment

logger = logging.getLogger("aura.rl")


def execute_experiment(project, actor, algorithm="q_learning", episodes=500, seed=7, max_steps=40):
    configuration = {
        "algorithm": algorithm,
        "episodes": episodes,
        "seed": seed,
        "max_steps": max_steps,
    }
    experiment = RLExperiment.objects.create(
        project=project,
        algorithm=algorithm,
        environment_version=ENVIRONMENT_VERSION,
        random_seed=seed,
        configuration_json=json.dumps(configuration, sort_keys=True),
        actor=actor,
        status="running",
        started_at=timezone.now(),
    )
    try:
        result = run_experiment(algorithm, episodes, seed, max_steps)
    except Exception as exc:
        logger.exception("RL experiment failed id=%s", experiment.id)
        experiment.status = "failed"
        experiment.error_summary = f"Experiment failed ({type(exc).__name__})."
        experiment.completed_at = timezone.now()
        experiment.save(update_fields=["status", "error_summary", "completed_at"])
        AuditEvent.objects.create(
            project=project,
            event_type="rl.experiment.failed",
            actor=actor,
            summary=f"RL experiment {experiment.id} failed.",
            details_json=json.dumps({"experiment_id": experiment.id, "error_type": type(exc).__name__}),
        )
        raise
    experiment.configuration_json = json.dumps(result["configuration"], sort_keys=True)
    experiment.metrics_json = json.dumps(result["metrics"], sort_keys=True)
    experiment.policy_json = json.dumps(result["policy"], sort_keys=True)
    experiment.policy_sha256 = result["policy_sha256"]
    experiment.status = "succeeded"
    experiment.completed_at = timezone.now()
    experiment.save(update_fields=[
        "configuration_json", "metrics_json", "policy_json", "policy_sha256",
        "status", "completed_at",
    ])
    return experiment, result
