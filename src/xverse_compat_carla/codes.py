"""Stable ``XVERSE-COMPAT-CARLA-*`` codes and their dispositions (detailed design §9.1)."""

from __future__ import annotations

FRAME = "XVERSE-COMPAT-CARLA-FRAME"
EPISODE = "XVERSE-COMPAT-CARLA-EPISODE"
SETTINGS = "XVERSE-COMPAT-CARLA-SETTINGS"
RANGE = "XVERSE-COMPAT-CARLA-RANGE"
SIZE = "XVERSE-COMPAT-CARLA-SIZE"
TIMESTAMP = "XVERSE-COMPAT-CARLA-TIMESTAMP"
COMMAND = "XVERSE-COMPAT-CARLA-COMMAND"
PROTOCOL = "XVERSE-COMPAT-CARLA-PROTOCOL"
SOURCE = "XVERSE-COMPAT-CARLA-SOURCE"

#: Codes after which the stream continues (no sequence number is consumed).
CONTINUE = frozenset({FRAME, RANGE, SIZE, TIMESTAMP, COMMAND})
#: Codes that end the run with exit 3 after a refusal and ``status: done``.
EXIT_3 = frozenset({EPISODE, SETTINGS, SOURCE})


class CarlaRefusal(Exception):
    """A refused sample, command or source state with a stable code."""

    def __init__(self, code: str, message: str, flow_id: str | None = None, frame: int | None = None) -> None:
        """Create the refusal (the message goes to stderr only)."""

        super().__init__(f"{code}: {message}")
        self.code = code
        self.flow_id = flow_id
        self.frame = frame

    def to_message(self) -> dict:
        """Return the protocol refusal ``{type, code, flowId, frame}``."""

        return {"type": "refusal", "code": self.code, "flowId": self.flow_id, "frame": self.frame}
