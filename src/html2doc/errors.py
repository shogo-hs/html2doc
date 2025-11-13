"""共通の例外定義。"""
from __future__ import annotations

from dataclasses import dataclass

from .models import HallucinationReport


@dataclass(slots=True)
class HallucinationError(RuntimeError):
    """ハルシネーション検出時に投げる例外。"""

    report: HallucinationReport

    def __post_init__(self) -> None:
        details = " / ".join(self.report.reasons or self.report.unsupported_passages)
        summary = (
            details
            or "生成結果に入力根拠が確認できない記述が含まれています。"
        )
        message = (
            "ハルシネーション検出"
            f" (安全度: {self.report.risk_score:.2f}): {summary}"
        )
        super().__init__(message)


__all__ = ["HallucinationError"]
