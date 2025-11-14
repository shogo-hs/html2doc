"""runner モジュール向けのユニットテスト。"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from html2doc.config import ConfigError, FileConfig
from html2doc.runner import _ensure_unique_output_stems


class EnsureUniqueOutputStemsTest(unittest.TestCase):
    """_ensure_unique_output_stems の振る舞いを検証する。"""

    def test_allows_unique_stems(self) -> None:
        """stem が重複しなければエラーにならない。"""

        with TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            files = [
                FileConfig(input=(base / "alpha" / "first.html")),
                FileConfig(input=(base / "beta" / "second.html")),
            ]

            _ensure_unique_output_stems(files)

    def test_detects_duplicate_stems(self) -> None:
        """stem が重複した場合は ConfigError を投げる。"""

        with TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            files = [
                FileConfig(input=(base / "x" / "manual.html")),
                FileConfig(input=(base / "y" / "manual.html")),
            ]

            with self.assertRaises(ConfigError) as ctx:
                _ensure_unique_output_stems(files)

        self.assertIn("manual", str(ctx.exception))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
