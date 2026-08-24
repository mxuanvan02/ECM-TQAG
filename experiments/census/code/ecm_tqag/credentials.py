"""Credential-path boundary for future authorized official execution.

Importing this module does not inspect environment variables or files.  The
runtime helper is called only after freeze/review verification and atomic
authorization consumption by an entrypoint.
"""
from __future__ import annotations
import contextlib, os, tempfile
from pathlib import Path
from typing import Iterator

@contextlib.contextmanager
def runtime_key_file(env_name: str) -> Iterator[Path]:
    value = os.environ.get(env_name, "").strip()
    if not value:
        raise ValueError("BLOCKED_OFFICIAL:CREDENTIAL_NOT_CONFIGURED:" + env_name)
    fd, name = tempfile.mkstemp(prefix="official-key-")
    path = Path(name)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, value.encode("utf-8"))
        os.close(fd)
        yield path
    finally:
        try: os.close(fd)
        except OSError: pass
        path.unlink(missing_ok=True)
