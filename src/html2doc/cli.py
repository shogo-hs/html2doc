"""html2doc CLI エントリポイント。"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Sequence

import typer
from typer.main import get_command

from .config import ConfigError
from .runner import DocumentResult, run

app = typer.Typer(
    help="HTML 応対マニュアルを LangGraph + OpenAI で Markdown へ変換するツール。",
    no_args_is_help=True,
)

LEGACY_OPTION_NAMES = {"--config", "-c", "--output-dir", "--inputs"}
LEGACY_PREFIXES = ("--config=", "--output-dir=", "--inputs=")


@app.callback()
def _cli_root() -> None:
    """html2doc CLI のルートコマンド。"""


def _execute_run(config: Path, output_dir: Optional[Path], input_list: Optional[Path]) -> None:
    """共通の実処理。"""

    try:
        results = run(config, output_override=output_dir, input_list=input_list)
    except ConfigError as exc:
        typer.secho(f"設定エラー: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    except RuntimeError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    success = sum(1 for item in results if item.success)
    failure = len(results) - success
    for item in results:
        if item.success:
            msg = f"[OK] {item.metadata.input_path} -> {item.output_path}"
            if item.graph_path:
                msg += f" (graph: {item.graph_path})"
            msg += _format_usage_suffix(item)
            typer.secho(msg, fg=typer.colors.GREEN)
        else:
            msg = f"[NG] {item.metadata.input_path}: {item.error}"
            msg += _format_usage_suffix(item)
            typer.secho(msg, fg=typer.colors.RED)

    typer.echo(f"成功 {success} 件 / 失敗 {failure} 件")
    if failure:
        raise typer.Exit(code=1)


@app.command(name="run")
def run_command(
    config: Path = typer.Option(..., "--config", "-c", help="変換対象を記述した YAML ファイルへのパス"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", help="出力先ディレクトリ（省略時は設定ファイルに従う）"),
    input_list: Optional[Path] = typer.Option(
        None,
        "--inputs",
        help="HTML ファイルのパスを列挙した YAML ファイル。`files` セクションと併用可能",
    ),
) -> None:
    """設定ファイルをもとに変換を実行する。"""

    _execute_run(config, output_dir, input_list)


def _contains_legacy_run_option(args: Sequence[str]) -> bool:
    for arg in args:
        if arg in LEGACY_OPTION_NAMES:
            return True
        if any(arg.startswith(prefix) for prefix in LEGACY_PREFIXES):
            return True
        if arg.startswith("-c") and arg not in {"-c", "--config"} and not arg.startswith("--"):
            return True
    return False


def _inject_legacy_command(args: Sequence[str]) -> list[str]:
    normalized = list(args)
    if not normalized:
        return normalized

    known_commands = {command.name for command in app.registered_commands}
    if normalized[0] in known_commands:
        return normalized

    if _contains_legacy_run_option(normalized):
        return ["run", *normalized]

    return normalized


def _format_usage_suffix(result: DocumentResult) -> str:
    tokens = []
    if result.usage_input_tokens is not None:
        tokens.append(f"in={result.usage_input_tokens}")
    if result.usage_output_tokens is not None:
        tokens.append(f"out={result.usage_output_tokens}")
    if not tokens:
        return ""
    return " [tokens " + " ".join(tokens) + "]"


def main(argv: Optional[Sequence[str]] = None) -> None:
    """Typer アプリのエントリーポイント。"""

    args = list(argv) if argv is not None else sys.argv[1:]
    prog_name = sys.argv[0] if argv is None else "html2doc"
    normalized = _inject_legacy_command(args)
    command = get_command(app)
    command.main(args=normalized, prog_name=prog_name, standalone_mode=True)


if __name__ == "__main__":  # pragma: no cover
    main()
