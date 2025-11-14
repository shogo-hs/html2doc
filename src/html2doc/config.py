"""設定ファイルの読み込みとバリデーションを担当するモジュール。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

import os
import yaml


class ConfigError(Exception):
    """設定ファイルの不備を表す例外。"""


@dataclass(slots=True)
class ModelConfig:
    """LLM 利用パラメータ。"""

    name: str = os.getenv("HTML2DOC_MODEL", "gpt-4.1-mini")
    temperature: float = 0.1
    top_p: Optional[float] = None
    max_output_tokens: Optional[int] = None


@dataclass(slots=True)
class FileConfig:
    """変換対象ファイルの設定。"""

    input: Path
    title: Optional[str] = None
    context: Optional[str] = None
    output: Optional[str] = None


@dataclass(slots=True)
class AppConfig:
    """CLI 全体の設定。"""

    model: ModelConfig = field(default_factory=ModelConfig)
    files: List[FileConfig] = field(default_factory=list)
    output_dir: Path = Path("output")

    def ensure_output_dir(self) -> Path:
        """出力ディレクトリを生成してパスを返す。"""

        self.output_dir.mkdir(parents=True, exist_ok=True)
        return self.output_dir


def _ensure_list(value: Any, *, field_name: str) -> list[Any]:
    if isinstance(value, list):
        return value
    raise ConfigError(f"`{field_name}` には配列を指定してください。")


def _resolve_path(raw_path: str | Path, base_dir: Path) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    return path


_DEFAULT_MODEL = ModelConfig()


def load_config(path: str | Path, *, allow_empty_files: bool = False) -> AppConfig:
    """YAML 設定ファイルを読み込み `AppConfig` を返す。"""

    config_path = Path(path).resolve()
    if not config_path.exists():
        raise ConfigError(f"設定ファイルが見つかりません: {config_path}")

    with config_path.open("r", encoding="utf-8") as file:
        try:
            raw = yaml.safe_load(file) or {}
        except yaml.YAMLError as exc:  # pragma: no cover - I/O 依存
            raise ConfigError("設定ファイルの読み込みに失敗しました。") from exc

    if not isinstance(raw, dict):
        raise ConfigError("YAML ルートはマッピングである必要があります。")

    base_dir = config_path.parent
    output_dir = raw.get("output", {}).get("dir") if isinstance(raw.get("output"), dict) else None
    model_section = raw.get("model") if isinstance(raw.get("model"), dict) else {}

    model = ModelConfig(
        name=str(model_section.get("name", _DEFAULT_MODEL.name)),
        temperature=float(model_section.get("temperature", _DEFAULT_MODEL.temperature)),
        top_p=float(model_section["top_p"]) if "top_p" in model_section else None,
        max_output_tokens=int(model_section["max_output_tokens"]) if "max_output_tokens" in model_section else None,
    )

    raw_files = _ensure_list(raw.get("files"), field_name="files") if "files" in raw else []
    if not raw_files and not allow_empty_files:
        raise ConfigError("`files` には 1 件以上のエントリーが必要です。")

    files: List[FileConfig] = []
    for idx, entry in enumerate(raw_files, start=1):
        if not isinstance(entry, dict):
            raise ConfigError(f"files[{idx}] はマッピングで指定してください。")
        if "input" not in entry:
            raise ConfigError(f"files[{idx}] に `input` がありません。")
        resolved_input = _resolve_path(entry["input"], base_dir)
        files.append(
            FileConfig(
                input=resolved_input,
                title=entry.get("title"),
                context=entry.get("context"),
                output=str(entry["output"]) if entry.get("output") else None,
            )
        )

    config = AppConfig(
        model=model,
        files=files,
        output_dir=_resolve_path(output_dir, base_dir) if output_dir else (base_dir / "output").resolve(),
    )
    return config


def load_file_list(path: str | Path) -> List[FileConfig]:
    """`files` セクションのみを切り出した YAML から `FileConfig` の配列を生成する。"""

    list_path = Path(path).resolve()
    if not list_path.exists():
        raise ConfigError(f"ファイルリストが見つかりません: {list_path}")

    with list_path.open("r", encoding="utf-8") as file:
        try:
            raw = yaml.safe_load(file) or []
        except yaml.YAMLError as exc:  # pragma: no cover - I/O 依存
            raise ConfigError("ファイルリストの読み込みに失敗しました。") from exc

    if isinstance(raw, dict):
        if "files" not in raw:
            raise ConfigError("ファイルリストの YAML は配列、または `files` キーを含む必要があります。")
        raw_entries = _ensure_list(raw["files"], field_name="files")
    else:
        raw_entries = _ensure_list(raw, field_name="files")

    if not raw_entries:
        raise ConfigError("ファイルリストに 1 件以上のエントリーを記載してください。")

    base_dir = list_path.parent
    files: List[FileConfig] = []
    for idx, entry in enumerate(raw_entries, start=1):
        output = None
        if isinstance(entry, (str, Path)):
            input_value = entry
            title = None
            context = None
        elif isinstance(entry, dict):
            if "input" not in entry:
                raise ConfigError(f"files[{idx}] に `input` がありません。")
            input_value = entry["input"]
            title = entry.get("title")
            context = entry.get("context")
            output = str(entry["output"]) if entry.get("output") else None
        else:
            raise ConfigError(f"files[{idx}] は文字列、または `input` を含むマッピングで指定してください。")

        resolved_input = _resolve_path(input_value, base_dir)
        files.append(
            FileConfig(
                input=resolved_input,
                title=title,
                context=context,
                output=output,
            )
        )

    return files


__all__ = [
    "AppConfig",
    "ConfigError",
    "FileConfig",
    "ModelConfig",
    "load_config",
    "load_file_list",
]
