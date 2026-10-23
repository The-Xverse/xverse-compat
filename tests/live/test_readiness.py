"""S1c-2 part 2 (S1c finding 40): the nonce-marker readiness announcement and the SIGTERM exit of the owned units.

Plain tests on temporary directories; no CARLA, no zenoh router. The native authority writes
``.xverse-ready/challenge`` (64 lowercase hex characters, mode 0400, no newline) in a unit's working directory
before release, and accepts only a regular 64-byte ``.xverse-ready/ready`` equal to it (platform S1b design,
``run_authority.c``). Here the challenge is written by the test in the same form.

The subprocess cases run the real unit entry points: the adapter on the pinned CPython 3.10 environment with
the fake source, the driver and the stimulus on this interpreter with a test-only zenoh stand-in
(``stub_zenoh/zenoh.py``). They check that each unit announces readiness and, once lingering, exits 0 on SIGTERM
well inside the declared 0.6 s grace.
"""

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time

import pytest

from xverse_compat.live import readiness as compat_readiness
from xverse_compat_carla import readiness as adapter_readiness

from ..carla.support import DESCRIPTORS, FIXTURES, ROOT, require_env

MODULES = pytest.mark.parametrize("module", [compat_readiness, adapter_readiness], ids=["xverse_compat", "xverse_compat_carla"])
STUB = Path(__file__).resolve().parent / "stub_zenoh"
GRACE_S = 0.6  # the declared process.stop.graceSeconds of every unit (blueprint harness)


def challenge(cwd: Path, nonce: bytes | None = None) -> bytes:
    """Create ``.xverse-ready/challenge`` as the native authority does (0700 directory, 0400 file)."""

    nonce = secrets.token_hex(32).encode() if nonce is None else nonce
    directory = cwd / ".xverse-ready"
    directory.mkdir(mode=0o700)
    (directory / "challenge").write_bytes(nonce)
    (directory / "challenge").chmod(0o400)
    return nonce


def test_both_copies_are_identical_after_the_docstring():
    def body(module):
        text = Path(inspect.getsourcefile(module)).read_text()
        return text[text.index('"""', 3) + 3:]

    assert body(compat_readiness) == body(adapter_readiness)


@MODULES
def test_challenge_present_is_answered_with_exactly_the_nonce(module, tmp_path):
    nonce = challenge(tmp_path)
    assert module.announce_ready(tmp_path) is True
    ready = tmp_path / ".xverse-ready" / "ready"
    assert ready.read_bytes() == nonce and len(nonce) == 64
    assert ready.is_file() and not ready.is_symlink() and ready.stat().st_mode & 0o777 == 0o600
    assert sorted(p.name for p in ready.parent.iterdir()) == ["challenge", "ready"]  # no temporary file is left


@MODULES
def test_default_cwd_is_the_working_directory(module, tmp_path, monkeypatch):
    nonce = challenge(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert module.announce_ready() is True and (tmp_path / ".xverse-ready" / "ready").read_bytes() == nonce


@MODULES
def test_no_challenge_does_nothing(module, tmp_path):
    assert module.announce_ready(tmp_path) is False and list(tmp_path.iterdir()) == []
    (tmp_path / ".xverse-ready").mkdir(mode=0o700)  # the directory without a challenge
    assert module.announce_ready(tmp_path) is False and list((tmp_path / ".xverse-ready").iterdir()) == []


@MODULES
@pytest.mark.parametrize("nonce", [b"a" * 63, b"a" * 65, b"a" * 64 + b"\n", b"A" * 64, b"g" * 64, b"0" * 63 + b" ", b""],
                         ids=["63", "65", "newline", "uppercase", "non-hex", "space", "empty"])
def test_malformed_challenge_is_refused_without_writing(module, tmp_path, nonce):
    challenge(tmp_path, nonce)
    with pytest.raises(module.ReadinessError):
        module.announce_ready(tmp_path)
    assert sorted(p.name for p in (tmp_path / ".xverse-ready").iterdir()) == ["challenge"]


@MODULES
def test_symlinked_challenge_is_refused(module, tmp_path):
    target = tmp_path / "elsewhere"
    target.write_bytes(secrets.token_hex(32).encode())
    (tmp_path / ".xverse-ready").mkdir(mode=0o700)
    (tmp_path / ".xverse-ready" / "challenge").symlink_to(target)
    with pytest.raises(module.ReadinessError):
        module.announce_ready(tmp_path)
    assert not (tmp_path / ".xverse-ready" / "ready").exists()


@MODULES
def test_symlinked_ready_directory_is_refused_and_its_target_untouched(module, tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    challenge(real)
    unit = tmp_path / "unit"
    unit.mkdir()
    (unit / ".xverse-ready").symlink_to(real / ".xverse-ready")
    with pytest.raises(module.ReadinessError):
        module.announce_ready(unit)
    assert sorted(p.name for p in (real / ".xverse-ready").iterdir()) == ["challenge"]


@MODULES
def test_existing_ready_symlink_is_replaced_never_followed(module, tmp_path):
    nonce = challenge(tmp_path)
    victim = tmp_path / "victim"
    victim.write_bytes(b"keep")
    (tmp_path / ".xverse-ready" / "ready").symlink_to(victim)
    assert module.announce_ready(tmp_path) is True
    ready = tmp_path / ".xverse-ready" / "ready"
    assert not ready.is_symlink() and ready.read_bytes() == nonce and victim.read_bytes() == b"keep"


@MODULES
def test_fifo_challenge_is_refused_without_blocking(module, tmp_path):
    (tmp_path / ".xverse-ready").mkdir(mode=0o700)
    os.mkfifo(tmp_path / ".xverse-ready" / "challenge")
    began = time.monotonic()
    with pytest.raises(module.ReadinessError):
        module.announce_ready(tmp_path)
    assert time.monotonic() - began < 1


@MODULES
def test_write_is_atomic_temporary_fsynced_then_renamed_in_the_same_directory(module, tmp_path, monkeypatch):
    nonce = challenge(tmp_path)
    directory = tmp_path / ".xverse-ready"
    calls = []
    real_fsync, real_replace = os.fsync, os.replace

    def fsync(fd):
        calls.append(("fsync", os.readlink(f"/proc/self/fd/{fd}")))
        return real_fsync(fd)

    def replace(src, dst, *, src_dir_fd=None, dst_dir_fd=None):
        # at the rename, ready does not exist yet and the complete nonce is in a temporary file of the same directory
        assert src_dir_fd == dst_dir_fd and os.readlink(f"/proc/self/fd/{src_dir_fd}") == str(directory)
        assert dst == "ready" and not (directory / "ready").exists() and "/" not in src
        assert (directory / src).read_bytes() == nonce
        calls.append(("replace", src))
        return real_replace(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)

    monkeypatch.setattr(module.os, "fsync", fsync)
    monkeypatch.setattr(module.os, "replace", replace)
    assert module.announce_ready(tmp_path) is True
    kinds = [c[0] for c in calls]
    assert kinds == ["fsync", "replace", "fsync"], calls  # file data before the rename, the directory after it
    assert calls[0][1] == str(directory / calls[1][1]) and calls[2][1] == str(directory)


@MODULES
def test_failed_rename_leaves_neither_ready_nor_a_temporary(module, tmp_path, monkeypatch):
    challenge(tmp_path)

    def replace(*args, **kwargs):
        raise OSError("injected")

    monkeypatch.setattr(module.os, "replace", replace)
    with pytest.raises(OSError, match="injected"):
        module.announce_ready(tmp_path)
    assert sorted(p.name for p in (tmp_path / ".xverse-ready").iterdir()) == ["challenge"]


def _wait(predicate, timeout_s: float, what: str):
    deadline = time.monotonic() + timeout_s
    while not predicate():
        assert time.monotonic() < deadline, f"timed out waiting for {what}"
        time.sleep(0.02)


def _term(proc: subprocess.Popen) -> float:
    """SIGTERM a lingering unit; return the seconds until it exited."""

    began = time.monotonic()
    proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=5)
    return time.monotonic() - began


_SOCKETS = []


def _socket_path() -> str:
    path = f"/run/user/{os.getuid()}/xverse-lite/test-ready-{os.getpid()}-{time.monotonic_ns()}.sock"
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    _SOCKETS.append(path)
    return path


@pytest.fixture(autouse=True)
def _remove_sockets():
    """The shared xverse-lite socket directory is part of the live residue check: leave nothing there (S1c finding 42)."""
    yield
    while _SOCKETS:
        Path(_SOCKETS.pop()).unlink(missing_ok=True)


def _unit_env(*paths) -> dict:
    return {"PATH": "/usr/bin", "HOME": "/nonexistent-home", "PYTHONPATH": os.pathsep.join(str(p) for p in paths)}


def test_driver_then_adapter_announce_readiness_and_exit_on_term(tmp_path):
    """The driver is ready before the adapter starts (Maestro starts the adapter after the driver's readiness);
    the adapter is ready once its source and link are up. Both exit 0 on SIGTERM inside the grace."""

    socket_path = _socket_path()
    driver_cwd, adapter_cwd = tmp_path / "work" / "lite-driver", tmp_path / "work" / "carla-adapter"
    driver_cwd.mkdir(parents=True)
    adapter_cwd.mkdir()
    driver_nonce, adapter_nonce = challenge(driver_cwd), challenge(adapter_cwd)
    driver = subprocess.Popen(
        [sys.executable, "-B", "-m", "xverse_compat.live.driver", "--socket", socket_path, "--descriptors", str(DESCRIPTORS),
         "--router", "tcp/127.0.0.1:1", "--run-dir", str(tmp_path / "driver"), "--episode-s", "1", "--tick-period-s", "0.05",
         "--accept-timeout-s", "30", "--marker", str(tmp_path / "work" / "driver.marker"), "--linger"],
        cwd=driver_cwd, env=_unit_env(STUB, ROOT / "src"), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    adapter = None
    try:
        _wait(lambda: (driver_cwd / ".xverse-ready" / "ready").exists() or driver.poll() is not None, 30, "the driver's ready")
        assert (driver_cwd / ".xverse-ready" / "ready").read_bytes() == driver_nonce
        adapter = subprocess.Popen(
            ["env", "-i", "PATH=/usr/bin", "HOME=/nonexistent-carla-home", "PYTHONPATH=" + str(ROOT / "src"), str(require_env()), "-s", "-B",
             "-m", "xverse_compat_carla.main", "--protocol", "2", "--connect", "unix:" + socket_path, "--source",
             f"fake:{FIXTURES / 'nominal.json'}", "--descriptors", str(DESCRIPTORS), "--linger",
             "--marker", str(tmp_path / "work" / "adapter.marker")],
            cwd=adapter_cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        markers = (tmp_path / "work" / "driver.marker", tmp_path / "work" / "adapter.marker")
        _wait(lambda: all(m.exists() for m in markers) or driver.poll() is not None or adapter.poll() is not None, 60, "both markers")
        assert (adapter_cwd / ".xverse-ready" / "ready").read_bytes() == adapter_nonce
        summary = json.loads((tmp_path / "driver" / "driver-summary.json").read_text())
        assert [json.loads(m.read_text())["code"] for m in markers] == [0, 0], summary.get("error")
        assert summary["readyAnnounced"] is True and summary["done"]["forbiddenModulesLoaded"] == []
        time.sleep(0.3)  # both lingering
        assert driver.poll() is None and adapter.poll() is None
        adapter_s, driver_s = _term(adapter), _term(driver)
        assert adapter.returncode == 0 and driver.returncode == 0, (adapter.stderr.read(), driver.stderr.read())
        assert adapter_s < GRACE_S and driver_s < GRACE_S, (adapter_s, driver_s)
    finally:
        for proc in (driver, adapter):
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.wait()


def test_stimulus_announces_readiness_and_exits_on_term(tmp_path):
    cwd = tmp_path / "work" / "driver-stimulus"
    cwd.mkdir(parents=True)
    nonce = challenge(cwd)
    marker = tmp_path / "work" / "stimulus.marker"
    proc = subprocess.Popen(
        [sys.executable, "-B", "-m", "xverse_compat.live.stimulus", "--router", "tcp/127.0.0.1:1", "--out", str(tmp_path / "s.jsonl"),
         "--time-base", "sim", "--period-s", "0.01", "--marker", str(marker), "--linger"],
        cwd=cwd, env=_unit_env(STUB, ROOT / "src"), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        _wait(lambda: marker.exists() or proc.poll() is not None, 30, "the stimulus marker")
        assert (cwd / ".xverse-ready" / "ready").read_bytes() == nonce
        assert json.loads(marker.read_text())["outcome"] == "profile-complete", proc.stderr
        time.sleep(0.3)
        assert proc.poll() is None
        seconds = _term(proc)
        assert proc.returncode == 0 and seconds < GRACE_S, (seconds, proc.stderr.read())
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def test_adapter_readiness_refusal_exits_3_before_the_protocol(tmp_path):
    """A malformed challenge is a visible adapter failure (exit 3, one stderr line), never a silent ready."""

    cwd = tmp_path / "unit"
    cwd.mkdir()
    challenge(cwd, b"x" * 64)
    proc = subprocess.run(
        ["env", "-i", "PATH=/usr/bin", "HOME=/nonexistent-carla-home", "PYTHONPATH=" + str(ROOT / "src"), str(require_env()), "-s", "-B",
         "-m", "xverse_compat_carla.main", "--source", f"fake:{FIXTURES / 'nominal.json'}", "--descriptors", str(DESCRIPTORS)],
        cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, timeout=30)
    assert proc.returncode == 3 and b"readiness" in proc.stderr and proc.stdout == b""
    assert not (cwd / ".xverse-ready" / "ready").exists()
