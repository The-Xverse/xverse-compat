"""Evaluation-only ground-truth export (FR-005; DYN-002): a JSON Lines file, never a protocol message."""

from __future__ import annotations

import json
from pathlib import Path


class GroundTruthExporter:
    """Append ``{frame, elapsedNs, actors}`` lines to an evaluation-only file."""

    def __init__(self, path) -> None:
        """Create (truncate) the export file."""

        self.path = Path(path)
        self.path.write_text("", encoding="utf-8")

    def write(self, frame: int, elapsed_ns: int, actors) -> None:
        """Append one frame of actor states (``id, type, x, y, z, vx, vy, vz``).

        ``None`` (actors not collected, e.g. a live source in Phase 4b) is refused rather than written as an
        empty scene (review 3 L5).
        """

        if actors is None:
            raise ValueError("ground-truth actors were not collected")

        line = json.dumps({"evaluationOnly": True, "frame": frame, "elapsedNs": elapsed_ns, "actors": list(actors)},
                          sort_keys=True, separators=(",", ":"), allow_nan=False)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")
