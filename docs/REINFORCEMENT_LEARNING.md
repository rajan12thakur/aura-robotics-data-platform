# Reinforcement-learning lab

## Implemented environment

AURA includes a small, deterministic `grid-pick-place-v1` task environment:

- A 3×3 grid has cells numbered row-major from 0 to 8.
- The gripper starts at cell 0, the object at cell 2, and the goal at cell 8.
- Actions are `up`, `down`, `left`, `right`, `pick`, and `place`.
- An episode succeeds when the gripper carries the object to the goal and
  places it. The step limit defaults to 40.
- Each ordinary step costs `-0.1`; invalid moves cost `-1`; a valid pick
  yields `+1.9`; successful placement yields `+19.9`.
- Boundary moves and invalid pick/place actions leave the state unchanged.
  The episode terminates at success or the step limit.

This is a tabular task abstraction, not a physics simulator. It does not model
robot geometry, camera observations, joint motion, obstacles, forces, or safety.
It must not be used as a physical robot controller.

## Learning and evaluation

`q_learning` uses a six-action tabular Q-function, epsilon-greedy exploration,
learning rate `0.2`, discount factor `0.95`, epsilon from `1.0` decaying to
`0.03`, and a caller-provided random seed. The local runner accepts 1–2,000
training episodes and 6–100 steps per episode. It stores bounded rolling
training reward/success summaries and the serialized Q-table.

Every run also evaluates the greedy policy on 20 episodes using a separate,
fixed seed range. A deterministic shortest-path baseline is evaluated over
the same number of episodes. The UI reports training separately from
evaluation and compares learned-policy success, mean reward, and steps with
the baseline. A `baseline` run is available to exercise the baseline alone.
Metrics are computed from actual simulator episodes, not from annotation
labels.

The simulator's task specification is distinct from annotation-derived task
visualization. Annotation sequences do not contain the state/action/reward
transitions required to train this policy. No behavior-cloning or
demonstration-to-policy training is claimed.

## Persistence and interfaces

Runs persist their project, algorithm, environment version, seed,
configuration, status, timestamps, metrics, policy JSON, and policy SHA-256
in the Django `RLExperiment` model. The authenticated API requires the
`ML Engineer`, `Project Manager`, or `Administrator` role to start a run:

- `GET /api/v1/rl/environment`
- `GET /api/v1/projects/{project_id}/rl-experiments`
- `POST /api/v1/projects/{project_id}/rl-experiments`
- `GET /api/v1/rl-experiments/{experiment_id}`

The POST payload accepts `algorithm` (`q_learning` or `baseline`), `episodes`,
`seed`, and `max_steps`. The runner is bounded and synchronous; the API stores
the run lifecycle and does not start background threads. For command-line use:

```powershell
python manage.py aura_run_rl --project-id <project-id> --algorithm q_learning --episodes 500 --seed 7
```

Assign the role with `python manage.py aura_assign_role <username> "ML Engineer"`.
The frontend's **Simulation** workspace contains the Q-learning and baseline
controls and displays persisted evaluation metrics and the training trend.

## Limitations

- This is a tiny deterministic environment; success here is not evidence of
  generalization, robotics capability, or sim-to-real transfer.
- Evaluation episodes share the fixed environment layout; the seed controls
  reproducible policy tie-breaking, not domain randomization.
- Runs are CPU-light and synchronous; no job queue, cancellation, or DQN is
  implemented.
- The policy checksum covers canonical JSON serialization of the Q-table. It
  is an integrity checksum, not a digital signature.
- The saved policy can be reloaded from the experiment detail API, but no
  hardware integration or policy deployment is provided.
