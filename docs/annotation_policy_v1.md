# AURA Annotation Policy 1.0

**Status:** Active local policy  
**Change note:** Initial version.

## Purpose and provenance

This policy provides AURA's default annotation guidance; it is not a
universal robotics standard. Every annotation must retain whether it
came from a human, an import, a model suggestion, or explicitly marked
synthetic demo data. Suggestions never become approved labels without a
human review decision.

## Default action vocabulary

| Label | Meaning |
|---|---|
| `approach` | The actor moves toward the target. |
| `reach` | The actor extends toward the target to interact. |
| `grasp` | The actor establishes a hold on the target. |
| `lift` | The held target is raised. |
| `move` | The held target is transported. |
| `place` | The target is positioned at its destination. |
| `release` | The actor lets go of the target. |
| `withdraw` | The actor moves away after interaction. |
| `inspect` | The actor visually or otherwise examines an item. |
| `other` | A meaningful action outside the vocabulary; explain it in notes. |

Use `other` and a concise note for an action that cannot be represented
by a known label. Do not guess an ambiguous action; leave it for review.

## Timestamp rules

Times are finite seconds from the beginning of the source video.
Intervals are half-open `[start_time, end_time)`: start must be
non-negative and end must be greater than start. Intervals that merely
touch at a boundary do not overlap. An end may exceed known duration by
at most 0.05 seconds to tolerate container rounding; such an excess is
still reported as an error. If duration is unknown, boundary checking
is unavailable and reported as an informational finding.

## Overlap and duplicates

Overlap is a warning requiring human inspection; it may be legitimate
for concurrent actions. Two segments are suspected duplicates when
their video, start, end, action, object, and actor values match after
normalizing case and whitespace. Do not automatically merge records.

## Confidence and severity

Confidence is optional and, when present, is a value in `[0,1]`. It is
an annotator/model-reported confidence, not a calibrated probability.
Missing/invalid required fields, invalid intervals, unknown references,
invalid confidence, and duplicate records are errors. Overlaps and
unknown input columns are warnings. Unavailable duration and an empty
dataset are informational or error conditions respectively; validation
results identify the actual severity.

## Review

New records are drafts. Approval is an explicit human decision and is
blocked when the latest project validation contains errors. Warnings
must be considered but do not automatically block approval. Model
suggestions require human review. A local reviewer display name is not
authentication.
