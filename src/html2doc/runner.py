"""LangGraph パイプライン実行のオーケストレーション。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

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

    _ensure_unique_output_stems(config.files)

    if output_override:
        config.output_dir = output_override.resolve()
    output_dir = config.ensure_output_dir()

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

        try:
            final_state = pipeline.invoke({"metadata": metadata})
            output_path = Path(final_state.get("output_path", metadata.output_path))
            graph_path_str = final_state.get("graph_path")
            graph_path = Path(graph_path_str) if graph_path_str else None
            results.append(
                DocumentResult(
                    metadata=metadata,
                    success=True,
                    output_path=output_path,
                    graph_path=graph_path,
                    report=final_state.get("report"),
                )
            )
        except Exception as exc:  # pragma: no cover - 外部 API 依存
            results.append(
                DocumentResult(
                    metadata=metadata,
                    success=False,
                    error=str(exc),
                )
            )

    return results


def _build_metadata(file_cfg: FileConfig, output_dir: Path) -> DocumentMetadata:
    stem = file_cfg.input.stem
    output_path = output_dir / f"{stem}.md"
    return DocumentMetadata(
        input_path=file_cfg.input,
        output_path=output_path,
        title=file_cfg.title,
        context=file_cfg.context,
    )


def _ensure_unique_output_stems(files: Iterable[FileConfig]) -> None:
    """stem が重複する入力ファイルを検出してエラーにする。"""

    collisions: dict[str, list[Path]] = {}
    for file_cfg in files:
        stem = file_cfg.input.stem
        collisions.setdefault(stem, []).append(file_cfg.input)

    duplicates = {stem: paths for stem, paths in collisions.items() if len(paths) > 1}
    if not duplicates:
        return

    summary = " / ".join(
        f"{stem}: {', '.join(str(path) for path in paths)}"
        for stem, paths in sorted(duplicates.items())
    )
    raise ConfigError(
        "同じファイル名 (stem) の HTML が複数指定されています。出力ファイルが上書きされるため、"
        "ファイル名を変更するか個別に実行してください。対象: "
        f"{summary}"
    )


__all__ = ["DocumentResult", "run"]
