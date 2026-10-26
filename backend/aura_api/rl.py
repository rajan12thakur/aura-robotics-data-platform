"""Small deterministic task-level grid environment and tabular Q-learning."""

from collections import defaultdict
import hashlib
import json
import random
from statistics import mean


ENVIRONMENT_VERSION = "grid-pick-place-v1"
GRID_WIDTH = 3
START_CELL = 0
OBJECT_CELL = 2
GOAL_CELL = 8
ACTION_NAMES = ("up", "down", "left", "right", "pick", "place")
MAX_EPISODES = 2000
MAX_STEPS = 100
EVALUATION_EPISODES = 20


class GridPickPlace:
    """A 3x3 discrete abstraction; it models no physical robot dynamics."""

    def __init__(self, max_steps=40):
        self.max_steps = max_steps
        self.reset()

    def reset(self):
        self.robot = START_CELL
        self.object_cell = OBJECT_CELL
        self.holding = False
        self.steps = 0
        self.done = False
        return self.state

    @property
    def state(self):
        return (self.robot, self.object_cell, int(self.holding))

    def step(self, action):
        if action not in ACTION_NAMES:
            raise ValueError(f"Unknown action: {action}")
        if self.done:
            raise RuntimeError("Episode is already complete; call reset first.")

        row, column = divmod(self.robot, GRID_WIDTH)
        next_cell = {
            "up": self.robot - GRID_WIDTH if row > 0 else None,
            "down": self.robot + GRID_WIDTH if row < GRID_WIDTH - 1 else None,
            "left": self.robot - 1 if column > 0 else None,
            "right": self.robot + 1 if column < GRID_WIDTH - 1 else None,
        }.get(action)
        reward = -0.1
        info = {"event": "step"}
        if action in ("up", "down", "left", "right"):
            if next_cell is None:
                reward, info["event"] = -1.0, "boundary"
            else:
                self.robot = next_cell
        elif action == "pick":
            if not self.holding and self.robot == self.object_cell:
                self.holding = True
                self.object_cell = -1
                reward, info["event"] = 1.9, "picked"
            else:
                reward, info["event"] = -1.0, "invalid_pick"
        elif action == "place":
            if self.holding and self.robot == GOAL_CELL:
                self.holding = False
                self.object_cell = self.robot
                reward, info["event"] = 19.9, "success"
                self.done = True
            else:
                reward, info["event"] = -1.0, "invalid_place"

        self.steps += 1
        if self.steps >= self.max_steps and not self.done:
            self.done = True
            info["event"] = "step_limit"
        return self.state, reward, self.done, info


def _state_key(state):
    return ",".join(str(value) for value in state)


def _select_action(q_table, state, epsilon, rng):
    if rng.random() < epsilon:
        return rng.randrange(len(ACTION_NAMES))
    values = q_table[state]
    best = max(values)
    choices = [index for index, value in enumerate(values) if value == best]
    return rng.choice(choices)


def _run_episode(env, policy, seed):
    state = env.reset()
    rng = random.Random(seed)
    reward_total = 0.0
    for _ in range(env.max_steps):
        action_index = policy(state, rng)
        state, reward, done, _ = env.step(ACTION_NAMES[action_index])
        reward_total += reward
        if done:
            break
    success = env.object_cell == GOAL_CELL and not env.holding
    return {"reward": round(reward_total, 4), "steps": env.steps, "success": success}


def _baseline_action(state, _rng):
    robot, object_cell, holding = state
    target = GOAL_CELL if holding else (object_cell if object_cell >= 0 else GOAL_CELL)
    robot_row, robot_column = divmod(robot, GRID_WIDTH)
    target_row, target_column = divmod(target, GRID_WIDTH)
    if robot_column < target_column:
        return ACTION_NAMES.index("right")
    if robot_column > target_column:
        return ACTION_NAMES.index("left")
    if robot_row < target_row:
        return ACTION_NAMES.index("down")
    if robot_row > target_row:
        return ACTION_NAMES.index("up")
    return ACTION_NAMES.index("place" if holding else "pick")


def _evaluation_summary(episodes):
    return {
        "episode_count": len(episodes),
        "success_rate": round(sum(item["success"] for item in episodes) / len(episodes), 4),
        "mean_reward": round(mean(item["reward"] for item in episodes), 4),
        "mean_steps": round(mean(item["steps"] for item in episodes), 4),
    }


def run_experiment(algorithm="q_learning", episodes=500, seed=7, max_steps=40):
    if algorithm not in ("q_learning", "baseline"):
        raise ValueError("algorithm must be q_learning or baseline.")
    if isinstance(episodes, bool) or not isinstance(episodes, int) or not 1 <= episodes <= MAX_EPISODES:
        raise ValueError(f"episodes must be between 1 and {MAX_EPISODES}.")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2**32 - 1:
        raise ValueError("seed must be an unsigned 32-bit integer.")
    if isinstance(max_steps, bool) or not isinstance(max_steps, int) or not 6 <= max_steps <= MAX_STEPS:
        raise ValueError(f"max_steps must be between 6 and {MAX_STEPS}.")

    q_table = defaultdict(lambda: [0.0] * len(ACTION_NAMES))
    rng = random.Random(seed)
    env = GridPickPlace(max_steps=max_steps)
    learning_rate, discount, initial_epsilon, minimum_epsilon = 0.2, 0.95, 1.0, 0.03
    episode_rows, curve = [], []

    if algorithm == "q_learning":
        for episode in range(episodes):
            state = env.reset()
            epsilon = max(minimum_epsilon, initial_epsilon * (1 - episode / episodes))
            reward_total = 0.0
            for step_number in range(max_steps):
                action = _select_action(q_table, state, epsilon, rng)
                next_state, reward, done, _ = env.step(ACTION_NAMES[action])
                next_max = 0.0 if done else max(q_table[next_state])
                old_value = q_table[state][action]
                q_table[state][action] = old_value + learning_rate * (
                    reward + discount * next_max - old_value
                )
                state = next_state
                reward_total += reward
                if done:
                    break
            episode_rows.append({
                "episode": episode + 1,
                "reward": round(reward_total, 4),
                "steps": step_number + 1,
                "success": env.object_cell == GOAL_CELL and not env.holding,
            })
            if (episode + 1) % max(1, episodes // 100) == 0 or episode == episodes - 1:
                window = episode_rows[-min(20, len(episode_rows)):]
                curve.append({
                    "episode": episode + 1,
                    "mean_reward": round(mean(row["reward"] for row in window), 4),
                    "success_rate": round(sum(row["success"] for row in window) / len(window), 4),
                })

    learned_policy = lambda state, local_rng: _select_action(q_table, state, 0, local_rng)
    baseline_episodes = [
        _run_episode(GridPickPlace(max_steps), _baseline_action, seed + offset)
        for offset in range(EVALUATION_EPISODES)
    ]
    learned_episodes = [
        _run_episode(GridPickPlace(max_steps), learned_policy if algorithm == "q_learning" else _baseline_action, seed + 10_000 + offset)
        for offset in range(EVALUATION_EPISODES)
    ]
    metrics = {
        "training": {
            "episodes": len(episode_rows),
            "mean_reward": round(mean(row["reward"] for row in episode_rows), 4) if episode_rows else None,
            "success_rate": round(sum(row["success"] for row in episode_rows) / len(episode_rows), 4) if episode_rows else None,
            "learning_curve": curve,
        },
        "evaluation": {
            "seed_start": seed + 10_000,
            "learned_policy": _evaluation_summary(learned_episodes),
            "baseline_policy": _evaluation_summary(baseline_episodes),
        },
    }
    policy = {
        _state_key(state): {ACTION_NAMES[index]: round(value, 6) for index, value in enumerate(values)}
        for state, values in sorted(q_table.items())
    }
    policy_sha256 = hashlib.sha256(
        json.dumps(policy, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "algorithm": algorithm,
        "environment_version": ENVIRONMENT_VERSION,
        "random_seed": seed,
        "configuration": {
            "episodes": episodes, "max_steps": max_steps,
            "learning_rate": learning_rate, "discount_factor": discount,
            "epsilon_start": initial_epsilon, "epsilon_min": minimum_epsilon,
            "evaluation_episodes": EVALUATION_EPISODES,
        },
        "metrics": metrics,
        "policy": policy,
        "policy_sha256": policy_sha256,
        "policy_state_count": len(policy),
        "limitations": [
            "This deterministic grid world is a task-level abstraction, not a physics simulator.",
            "The learned policy is not a robot controller and has no real-world safety or transfer guarantees.",
            "Annotations are not RL transitions; Q-learning learns from simulator rewards and next states.",
        ],
    }
