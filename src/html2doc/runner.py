"""CLI から呼び出される実行ロジック。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .config import FileConfig, load_config
from .errors import HallucinationError
from .graph import build_pipeline
from .llm import MarkdownGenerator
from .models import DocumentMetadata, HallucinationReport, ValidationReport


@dataclass(slots=True)
class DocumentResult:
    """1 ファイル処理の結果。"""

    metadata: DocumentMetadata
    success: bool
    output_path: Optional[Path] = None
    graph_path: Optional[Path] = None
    report: Optional[ValidationReport] = None
    hallucination_report: Optional[HallucinationReport] = None
    error: Optional[str] = None


def run(config_path: Path, *, output_override: Optional[Path] = None) -> List[DocumentResult]:
    """設定ファイルを読み込み、LangGraph パイプラインを実行する。"""

    config = load_config(config_path)
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
                    hallucination_report=final_state.get("hallucination_report"),
                )
            )
        except HallucinationError as exc:
            results.append(
                DocumentResult(
                    metadata=metadata,
                    success=False,
                    hallucination_report=exc.report,
                    error=str(exc),
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


__all__ = ["DocumentResult", "run"]
