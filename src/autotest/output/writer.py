"""File writer for generated tests.

Writes test code to disk with directory creation, atomic temp-file +
rename, and an optional formatter pass (Pint for PHP). Atomicity keeps
half-written test files from existing on disk if the process dies mid-
write -- the same temp+rename pattern we use in Ichava's IconsManifest.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class WriteResult:
    """Where the test landed + whether formatting succeeded."""

    path: Path
    formatted: bool
    formatter_stderr: str = ""


def write_test(
    path: Path,
    content: str,
    formatter_cmd: list[str] | None = None,
    formatter_cwd: Path | None = None,
) -> WriteResult:
    """Atomic-write ``content`` to ``path``, then optionally format it.

    ``formatter_cmd`` is a list like ``["vendor/bin/pint"]`` -- the path is
    appended automatically. If the formatter is missing or fails we still
    return success on the write; formatting is best-effort, never required.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp." + os.urandom(4).hex())
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)

    formatter_stderr = ""
    formatted = False
    if formatter_cmd:
        try:
            proc = subprocess.run(
                [*formatter_cmd, str(path)],
                cwd=formatter_cwd or path.parent,
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
            formatted = proc.returncode == 0
            if not formatted:
                formatter_stderr = (proc.stderr or proc.stdout or "").strip()
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            formatter_stderr = f"Formatter unavailable: {e}"

    return WriteResult(path=path, formatted=formatted, formatter_stderr=formatter_stderr)


def remove_test(path: Path) -> None:
    """Best-effort delete. Used when the runner rejects a candidate."""
    with contextlib.suppress(FileNotFoundError):
        path.unlink()
