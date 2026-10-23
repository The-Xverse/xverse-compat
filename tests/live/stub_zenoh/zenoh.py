"""Test-only stand-in for eclipse-zenoh, put first on PYTHONPATH by ``test_readiness.py`` so that the owned
units' readiness and SIGTERM paths run without a router. Publishers drop values; a ``clock_status``
subscriber is fed an increasing simulation time (0.25 s every 5 ms) until the session is closed."""

import threading
import time


class Config:
    def insert_json5(self, key, value):
        pass


class _Payload:
    def __init__(self, data):
        self._data = data

    def to_bytes(self):
        return self._data


class _Sample:
    def __init__(self, value):
        self.payload = _Payload(str(value).encode())


class _Publisher:
    def put(self, value):
        pass


class Session:
    def __init__(self):
        self.closed = False

    def declare_publisher(self, key):
        return _Publisher()

    def declare_subscriber(self, key, callback):
        if key.endswith("clock_status"):
            def feed():
                value = 0.0
                while not self.closed:
                    callback(_Sample(value))
                    value += 0.25
                    time.sleep(0.005)
            threading.Thread(target=feed, daemon=True).start()
        return object()

    def close(self):
        self.closed = True


def open(config):  # noqa: A001 - the zenoh API name
    return Session()
