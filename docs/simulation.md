# AURA task-level simulation

The simulation feature stores a versioned task representation derived from
saved annotation action labels, source annotation IDs, timestamps, and object
labels. Pick-and-place phases are `approach`, `reach`, `grasp`, `lift`, `move`,
`place`, `release`, and `withdraw`. Missing phases are shown as missing;
unmapped labels remain visible.

The local visualization advances one saved phase per user action and can be
reset. It does not infer coordinates or robot motion. It does not model real
robot geometry, camera calibration, joint trajectories, gripper commands,
force/tactile sensing, collision planning, or physical grasping. Video action
labels alone cannot train or control a robot.

A future real robotics integration would require calibrated scene/object
poses, a robot-specific action representation, safety validation, collision
planning, hardware/simulator integration, and independent safety review.

## Separate grid-world learning lab

The Simulation workspace also provides `grid-pick-place-v1`, a separate
deterministic 3×3 environment for tabular Q-learning and baseline evaluation.
It does not drive or train from the annotation-derived phase visualization
described above. See [Reinforcement learning](./REINFORCEMENT_LEARNING.md) for
the environment, reward rules, persisted run metadata, and limitations.
