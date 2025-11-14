"""CLI 関連のテスト。"""
from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from typer.testing import CliRunner

from html2doc import cli


class CliTestCase(unittest.TestCase):
    """Typer CLI の動作検証。"""

    runner = CliRunner()

    @staticmethod
    def _write_dummy(path: Path) -> None:
        path.write_text("files: []\n", encoding="utf-8")

    def test_run_subcommand_invokes_runner(self) -> None:
        with self.runner.isolated_filesystem():
            base = Path.cwd()
            config = base / "config.yaml"
            inputs = base / "inputs.yaml"
            output_dir = base / "out"
            self._write_dummy(config)
            self._write_dummy(inputs)

            with patch("html2doc.cli.run", return_value=[]) as mock_run:
                result = self.runner.invoke(
                    cli.app,
                    [
                        "run",
                        "--config",
                        str(config),
                        "--output-dir",
                        str(output_dir),
                        "--inputs",
                        str(inputs),
                    ],
                )

            self.assertEqual(result.exit_code, 0)
            mock_run.assert_called_once()
            called_config = mock_run.call_args.args[0]
            self.assertEqual(called_config, config)
            self.assertEqual(mock_run.call_args.kwargs["output_override"], output_dir)
            self.assertEqual(mock_run.call_args.kwargs["input_list"], inputs)

    def test_main_accepts_legacy_invocation(self) -> None:
        with self.runner.isolated_filesystem():
            config = Path("config.yaml")
            self._write_dummy(config)

            with patch("html2doc.cli.run", return_value=[]) as mock_run:
                with self.assertRaises(SystemExit) as ctx:
                    cli.main(["--config", str(config)])

            self.assertEqual(ctx.exception.code, 0)
            mock_run.assert_called_once()
            self.assertEqual(mock_run.call_args.args[0], config)
            self.assertIsNone(mock_run.call_args.kwargs["output_override"])
            self.assertIsNone(mock_run.call_args.kwargs["input_list"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
