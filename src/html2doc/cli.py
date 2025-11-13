"""html2doc CLI エントリポイント。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from .config import ConfigError
from .runner import run

app = typer.Typer(help="HTML 応対マニュアルを LangGraph + OpenAI で Markdown へ変換するツール。")


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
            typer.secho(msg, fg=typer.colors.GREEN)
        else:
            typer.secho(
                f"[NG] {item.metadata.input_path}: {item.error}",
                fg=typer.colors.RED,
            )

    typer.echo(f"成功 {success} 件 / 失敗 {failure} 件")
    if failure:
        raise typer.Exit(code=1)


def main() -> None:
    """Typer アプリのエントリーポイント。"""

    app()


if __name__ == "__main__":  # pragma: no cover
    main()
