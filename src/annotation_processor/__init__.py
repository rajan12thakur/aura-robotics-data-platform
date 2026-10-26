"""Framework-independent annotation import, validation, and reporting."""

from .dataset import load_annotations
from .validation import ACTION_LABELS, validate_annotations

__all__ = ["ACTION_LABELS", "load_annotations", "validate_annotations"]
