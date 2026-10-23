"""Nonce-marker readiness announcement for owned Maestro units (S1 FR-011, platform S1b; S1c finding 40).

When a unit declares the ``nonce-marker`` observe condition, the native run authority creates
``.xverse-ready/challenge`` in the unit's working directory before the unit is released: 64 lowercase hex
characters, no newline. The unit announces that it is ready by writing exactly those 64 bytes to
``.xverse-ready/ready``. The authority accepts only a regular file of exactly 64 bytes equal to the nonce.

``announce_ready`` writes the marker atomically (a temporary file in the same directory, ``fsync``, then
``os.replace``) and never follows a symbolic link. Without a challenge it does nothing and returns False.
A challenge that is present but malformed (not a regular file, not 64 lowercase hex bytes, a linked
directory) raises ``ReadinessError``; the unit's own failure path then makes it visible.

The CPython 3.10 adapter package must not import ``xverse_compat`` (``xverse_compat_carla.protocol.FORBIDDEN``),
so ``xverse_compat_carla.readiness`` carries the same function; ``tests/live/test_readiness.py`` checks that
both copies are identical.
"""

from __future__ import annotations

import os
import secrets
import stat

READY_DIRECTORY = ".xverse-ready"
CHALLENGE = "challenge"
READY = "ready"
NONCE_BYTES = 64
_HEX = frozenset(b"0123456789abcdef")


class ReadinessError(OSError):
    """A challenge exists but cannot be answered safely."""


def announce_ready(cwd=None) -> bool:
    """Answer the native readiness challenge in ``cwd`` (default: the working directory).

    Returns True when ``ready`` was written, False when there is no challenge."""

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
    base = os.open("." if cwd is None else os.fspath(cwd), flags)
    try:
        try:
            directory = os.open(READY_DIRECTORY, flags | os.O_NOFOLLOW, dir_fd=base)
        except FileNotFoundError:
            return False
        except OSError as error:  # a symlink (ELOOP) or a non-directory (ENOTDIR)
            raise ReadinessError(f"{READY_DIRECTORY} is not a plain directory: {error}") from None
        try:
            try:
                fd = os.open(CHALLENGE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
            except FileNotFoundError:
                return False
            except OSError as error:  # a symlink (ELOOP) or an unreadable entry
                raise ReadinessError(f"challenge cannot be opened: {error}") from None
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_size != NONCE_BYTES:
                    raise ReadinessError("challenge is not a regular file of 64 bytes")
                nonce = b""
                while len(nonce) <= NONCE_BYTES:
                    chunk = os.read(fd, NONCE_BYTES + 1 - len(nonce))
                    if not chunk:
                        break
                    nonce += chunk
            finally:
                os.close(fd)
            if len(nonce) != NONCE_BYTES or not set(nonce) <= _HEX:
                raise ReadinessError("challenge is not 64 lowercase hex characters")
            temporary = f".{READY}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
            out = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600,
                          dir_fd=directory)
            try:
                try:
                    view = memoryview(nonce)
                    while view:
                        view = view[os.write(out, view):]
                    os.fsync(out)
                finally:
                    os.close(out)
                # rename(2) replaces the name ``ready`` itself; an existing link there is never followed
                os.replace(temporary, READY, src_dir_fd=directory, dst_dir_fd=directory)
            except BaseException:
                try:
                    os.unlink(temporary, dir_fd=directory)
                except OSError:
                    pass
                raise
            os.fsync(directory)
            return True
        finally:
            os.close(directory)
    finally:
        os.close(base)
