"""LangGraph パイプライン実行のオーケストレーション。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .config import ConfigError, FileConfig, load_config, load_file_list
from .graph import build_pipeline
from .llm import MarkdownGenerator
from .models import DocumentMetadata, ValidationReport


@dataclass(slots=True)
class DocumentResult:
    """1 ファイル処理の結果。"""

    metadata: DocumentMetadata
    success: bool
    output_path: Optional[Path] = None
    graph_path: Optional[Path] = None
    report: Optional[ValidationReport] = None
    error: Optional[str] = None
    usage_input_tokens: Optional[int] = None
    usage_output_tokens: Optional[int] = None


def run(
    config_path: Path,
    *,
    output_override: Optional[Path] = None,
    input_list: Optional[Path] = None,
) -> List[DocumentResult]:
    """設定ファイルを読み込み、LangGraph パイプラインを実行する。"""

    config = load_config(config_path, allow_empty_files=input_list is not None)
    if input_list:
        extra_files = load_file_list(input_list)
        config.files = [*config.files, *extra_files]
    if not config.files:
        raise ConfigError("`files` または --inputs には 1 件以上のエントリーが必要です。")

    if output_override:
        config.output_dir = output_override.resolve()
    output_dir = config.ensure_output_dir()

    _ensure_unique_output_paths(config.files, output_dir)

    llm = MarkdownGenerator(config.model)
    pipeline = build_pipeline(llm)

    results: List[DocumentResult] = []
    for file_cfg in config.files:
        metadata = _build_metadata(file_cfg, output_dir)
        if not metadata.input_path.exists():
            results.append(
                DocumentResult(
                    metadata=metadata,
                    success=False,
                    error=f"入力ファイルが見つかりません: {metadata.input_path}",
                )
            )
            continue

        usage_before = llm.snapshot_usage()
        try:
            final_state = pipeline.invoke({"metadata": metadata})
            output_path = Path(final_state.get("output_path", metadata.output_path))
            graph_path_str = final_state.get("graph_path")
            graph_path = Path(graph_path_str) if graph_path_str else None
            usage_delta = _usage_delta(usage_before, llm.snapshot_usage())
            results.append(
                DocumentResult(
                    metadata=metadata,
                    success=True,
                    output_path=output_path,
                    graph_path=graph_path,
                    report=final_state.get("report"),
                    usage_input_tokens=usage_delta.get("input_tokens"),
                    usage_output_tokens=usage_delta.get("output_tokens"),
                )
            )
        except Exception as exc:  # pragma: no cover - 外部 API 依存
            usage_delta = _usage_delta(usage_before, llm.snapshot_usage())
            results.append(
                DocumentResult(
                    metadata=metadata,
                    success=False,
                    error=str(exc),
                    usage_input_tokens=usage_delta.get("input_tokens"),
                    usage_output_tokens=usage_delta.get("output_tokens"),
                )
            )

    return results


def _build_metadata(file_cfg: FileConfig, output_dir: Path) -> DocumentMetadata:
    output_path = _resolve_output_path(file_cfg, output_dir)
    return DocumentMetadata(
        input_path=file_cfg.input,
        output_path=output_path,
        title=file_cfg.title,
        context=file_cfg.context,
    )


def _resolve_output_path(file_cfg: FileConfig, output_dir: Path) -> Path:
    """ファイル設定から最終出力パスを算出する。"""

    if file_cfg.output:
        candidate = Path(file_cfg.output)
        return candidate if candidate.is_absolute() else (output_dir / candidate).resolve()
    return (output_dir / f"{file_cfg.input.stem}.md").resolve()


def _ensure_unique_output_paths(files: Iterable[FileConfig], output_dir: Path) -> None:
    """最終的に生成される出力パスの重複を検出する。"""

    collisions: dict[Path, list[Path]] = {}
    for file_cfg in files:
        resolved = _resolve_output_path(file_cfg, output_dir)
        collisions.setdefault(resolved, []).append(file_cfg.input)

    duplicates = {path: inputs for path, inputs in collisions.items() if len(inputs) > 1}
    if not duplicates:
        return

    summary = " / ".join(
        f"{path}: {', '.join(str(src) for src in inputs)}" for path, inputs in sorted(duplicates.items())
    )
    raise ConfigError(
        "同じ出力ファイルに複数の HTML が割り当てられています。`output` を変更して回避してください。対象: "
        f"{summary}"
    )


def _usage_delta(before: Dict[str, int], after: Dict[str, int]) -> Dict[str, int]:
    keys = {"input_tokens", "output_tokens"}
    return {key: max(0, after.get(key, 0) - before.get(key, 0)) for key in keys}


__all__ = ["DocumentResult", "run"]
