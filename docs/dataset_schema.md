# Dataset schema 1.0

Canonical CSV columns are `video_id,start_time,end_time,action_label,
object_label,actor_id,confidence,notes`. Required: `video_id`,
`start_time`, `end_time`, `action_label`. Optional blank fields are
stored as null/empty values. Unknown columns are preserved only as
import warnings; they are not silently treated as known metadata.

JSON accepts an array of records or
`{"schema_version":"1.0","annotations":[...]}`. Times are finite seconds
and intervals use half-open `[start,end)`. Confidence, when supplied,
is in `[0,1]`. API records also carry stable IDs, provenance, review
state, and revision.

The synthetic fixture at `data/examples/sample_annotations.csv` is
fabricated for product demonstration and does not refer to a real video.

Validation codes: `MISSING_REQUIRED_FIELD`, `INVALID_START_TIME`,
`INVALID_END_TIME`, `NEGATIVE_START_TIME`, `NON_POSITIVE_INTERVAL`,
`END_EXCEEDS_VIDEO_DURATION`, `UNKNOWN_ACTION_LABEL`,
`INVALID_CONFIDENCE`, `DUPLICATE_ANNOTATION`,
`OVERLAPPING_INTERVAL`, `UNKNOWN_VIDEO_REFERENCE`,
`VIDEO_PROJECT_MISMATCH`, `UNKNOWN_COLUMNS`, `EMPTY_DATASET`,
`VIDEO_DURATION_UNAVAILABLE`, and `SUSPICIOUS_INTERVAL_DURATION`.
