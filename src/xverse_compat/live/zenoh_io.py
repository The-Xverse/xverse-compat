"""Zenoh client sessions for the owned live units (eclipse-zenoh 1.3.4, the legacy clients' version).

Owned units connect in client mode to one explicit router endpoint with multicast scouting disabled.
Payloads follow the legacy encoding: ``str(float)`` for float32 and ``"true"``/``"false"`` for booleans.
"""

from __future__ import annotations

import json
import threading
import time


def open_session(router: str):
    """Open a client session to ``router`` (e.g. ``tcp/127.0.0.1:7447``)."""

    import zenoh  # noqa: PLC0415 - only the live units need zenoh

    config = zenoh.Config()
    config.insert_json5("mode", json.dumps("client"))
    config.insert_json5("connect/endpoints", json.dumps([router]))
    config.insert_json5("scouting/multicast/enabled", "false")
    return zenoh.open(config)


class Latest:
    """The latest float value received on a key, with its host-monotonic receipt time."""

    def __init__(self, session, key: str, default: float) -> None:
        self.key, self.value, self.received_ns, self.count = key, default, None, 0
        self._lock = threading.Lock()
        self._sub = session.declare_subscriber(key, self._on)

    def _on(self, sample) -> None:
        try:
            value = float(sample.payload.to_bytes().decode("utf-8"))
        except ValueError:
            return
        with self._lock:
            self.value, self.received_ns, self.count = value, time.monotonic_ns(), self.count + 1

    def read(self) -> tuple[float, int | None, int]:
        with self._lock:
            return self.value, self.received_ns, self.count


def redirect_stderr(argv) -> None:
    """``--stderr FILE``: append this unit's diagnostics to FILE (Maestro units have ``/dev/null`` streams)."""

    if "--stderr" in argv:
        import os  # noqa: PLC0415

        path = argv[argv.index("--stderr") + 1]
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.dup2(fd, 2)
        os.close(fd)
        del argv[argv.index("--stderr"):argv.index("--stderr") + 2]
