"""runner モジュール向けのユニットテスト。"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from html2doc.config import ConfigError, FileConfig
from html2doc.runner import _ensure_unique_output_paths


class EnsureUniqueOutputPathsTest(unittest.TestCase):
    """_ensure_unique_output_paths の振る舞いを検証する。"""

    def test_allows_unique_targets(self) -> None:
        """最終出力がユニークであればエラーにならない。"""

        with TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            output_dir = base / "out"
            output_dir.mkdir()
            files = [
                FileConfig(input=(base / "alpha" / "first.html")),
                FileConfig(input=(base / "beta" / "second.html")),
            ]

            _ensure_unique_output_paths(files, output_dir)

    def test_detects_duplicate_targets(self) -> None:
        """同じ出力パスになる場合は ConfigError を投げる。"""

        with TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            output_dir = base / "out"
            output_dir.mkdir()
            files = [
                FileConfig(input=(base / "x" / "manual.html")),
                FileConfig(input=(base / "y" / "manual.html")),
            ]

            with self.assertRaises(ConfigError) as ctx:
                _ensure_unique_output_paths(files, output_dir)

        self.assertIn("manual", str(ctx.exception))

    def test_allows_explicit_overrides(self) -> None:
        """`output` で別名を指定すれば stem が重複しても許容される。"""

        with TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            output_dir = base / "out"
            output_dir.mkdir()
            files = [
                FileConfig(input=(base / "x" / "manual.html"), output="alpha.md"),
                FileConfig(input=(base / "y" / "manual.html"), output="beta.md"),
            ]

            _ensure_unique_output_paths(files, output_dir)

    def test_detects_explicit_conflicts(self) -> None:
        """同じ `output` を割り当てた場合はエラーになる。"""

        with TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            output_dir = base / "out"
            output_dir.mkdir()
            files = [
                FileConfig(input=(base / "x" / "manual.html"), output="duplicate.md"),
                FileConfig(input=(base / "y" / "manual.html"), output="duplicate.md"),
            ]

            with self.assertRaises(ConfigError):
                _ensure_unique_output_paths(files, output_dir)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
