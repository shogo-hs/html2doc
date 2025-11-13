"""環境変数の読み込みユーティリティ。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional


def load_env(dotenv_path: str | Path | None = None) -> None:
    """`.env` ファイルを読み込み、未設定の環境変数を登録する。"""

    path = _resolve_path(dotenv_path)
    if not path:
        return

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for line in lines:
        key, value = _parse_line(line)
        if not key:
            continue
        if key in os.environ:
            continue
        os.environ[key] = value


def _resolve_path(dotenv_path: str | Path | None) -> Optional[Path]:
    if dotenv_path:
        path = Path(dotenv_path).expanduser().resolve()
        return path if path.is_file() else None

    current = Path.cwd().resolve()
    for directory in _iter_dirs(current):
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
    return None


def _iter_dirs(start: Path) -> Iterable[Path]:
    directory = start
    yield directory
    for parent in directory.parents:
        yield parent


def _parse_line(line: str) -> tuple[str, str]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return "", ""
    if stripped.lower().startswith("export "):
        stripped = stripped[7:].lstrip()
    if "=" not in stripped:
        return "", ""
    key, raw_value = stripped.split("=", 1)
    key = key.strip()
    value = raw_value.strip().strip('"').strip("'")
    return key, value


__all__ = ["load_env"]
