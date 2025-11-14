# html2doc

LangGraph と OpenAI を使い、ローカルにある HTML 応対マニュアルを Markdown へ変換する CLI ツールです。

## セットアップ
1. `.env.example` をコピーして `.env` を作成し、`OPENAI_API_KEY`（必要に応じて `HTML2DOC_MODEL`）を設定します。
2. 依存インストール: `uv sync`
3. 以降のコマンドは `uv run html2doc run ...` で実行します（ヘルプ確認は `uv run html2doc run --help`）。

## 使い方
1. `.env` で設定した OpenAI API キーが読み込まれていることを確認します（CLI 起動時に自動で読み込まれます）。
2. 共通設定 (`config.yaml`) を作成します。通常はモデル指定と出力ディレクトリのみで十分です。
   ```yaml
   model:
     name: gpt-4.1-mini
     temperature: 0.1
   output:
     dir: ./outputs
   ```
3. 変換対象リスト (`inputs.yaml`) を記述します。`output` フィールドを指定すると出力ファイル名（または `output.dir` 配下の相対パス）を任意に設定できます。
   ```yaml
   - input: data/manual_a.html
     title: "Aマニュアル"
     context: "VIP 顧客向けハンドブック"
     output: vip-guide.md
   - input: data/manual_b.html
     output: branch/b_manual.md
   - data/manual_c.html  # 文字列だけでも指定可能（出力は c.md）
   ```
4. CLI を実行します（出力先は `config.yaml` で指定した `output.dir`）。
   ```bash
   uv run html2doc run --config config.yaml --inputs inputs.yaml
   # `config.yaml` に files を直接書いた場合
   uv run html2doc run --config config.yaml
   # 任意で出力先を指定
   uv run html2doc run --config config.yaml --output-dir build/output
   ```

## 主な機能
- LangGraph StateGraph で `load_html → parse_html → extract_knowledge → link_relations → compose_markdown → check_hallucination → validate_output → persist_markdown` を順次実行。
- BeautifulSoup で HTML をセクション・アセット単位に分解し、OpenAI `gpt-4.1-mini` でナレッジ抽出・関係推定・Markdown 合成を行う。
- 生成結果に対して LLM ベースのハルシネーション検知を行い、ソースに存在しない記述を捕捉した場合は検証フェーズで失敗させる。
- 生成した Markdown とあわせて、ナレッジグラフ（sections / knowledge / relationships / validation）を `<stem>.json` として保存。
- 各処理完了後に、使用した OpenAI トークン（input / output）をファイルごとに CLI へ表示。
- HTML ファイル名の stem をそのまま出力名に採用し、`output/<stem>.md` + `output/<stem>.json` を生成。
- 失敗があっても他ファイルの処理を継続し、成功/失敗サマリを CLI に表示。

## 出力アーティファクト
- `output/<stem>.md`: LangGraph + OpenAI で整形した Markdown。
- `output/<stem>.json`: セクション構成・抽出ナレッジ・関係エッジ・検証結果を含む補助ファイル（RAG のインデックス投入を想定）。

## トラブルシューティング
- `OPENAI_API_KEY` 未設定: CLI が即座にエラー終了します。`.env` もしくは環境変数を確認してください。
- YAML 形式エラー: エラーメッセージに該当箇所が表示されます。`files` が配列か、`input` が存在するかをご確認ください。
