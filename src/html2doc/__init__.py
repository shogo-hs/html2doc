"""html2doc パッケージ。"""

from __future__ import annotations

from .env import load_env

# `.env` を自動読み込みして API キーやモデル設定を環境変数で扱う。
# 既存の環境変数を上書きしないため、未設定の変数のみ追加する。
load_env()

__all__ = []
