"""Common interface for detection layers (heuristic and classifier)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from injection_defense.schemas import DetectionResult


class Detector(ABC):
    """Inspects untrusted text and reports. It never decides what to do about it:
    blocking/sanitizing is policy, applied by the pipeline."""

    layer: str

    @abstractmethod
    def detect(self, text: str) -> DetectionResult: ...
