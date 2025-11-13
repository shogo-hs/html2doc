# html2doc

LangGraph と OpenAI を使い、ローカルにある HTML 応対マニュアルを Markdown へ変換する CLI ツールです。

## セットアップ
1. 依存インストール: `uv sync`
2. 以降のコマンドは `uv run ...` で実行します（例: `uv run html2doc --help`）。

## 使い方
1. OpenAI API キーを環境変数に設定します。
   ```bash
   export OPENAI_API_KEY="sk-..."
   ```
2. 変換対象を YAML ファイルに記述します。
   ```yaml
   model:
     name: gpt-4.1-mini
     temperature: 0.1
   files:
     - input: data/manual_a.html
       title: "Aマニュアル"
       context: "VIP 顧客向けハンドブック"
     - input: data/manual_b.html
   ```
3. CLI を実行します（出力先は既定で `output/`）。
   ```bash
   uv run html2doc run --config config.yaml
   # 任意で出力先を指定
   uv run html2doc run --config config.yaml --output-dir build/output
   ```

## 主な機能
- LangGraph StateGraph で `load_html → parse_html → extract_knowledge → link_relations → compose_markdown → validate_output → persist_markdown` を順次実行。
- BeautifulSoup で HTML をセクション・アセット単位に分解し、OpenAI `gpt-4.1-mini` でナレッジ抽出・関係推定・Markdown 合成を行う。
- 生成した Markdown とあわせて、ナレッジグラフ（sections / knowledge / relationships / validation）を `<stem>.json` として保存。
- HTML ファイル名の stem をそのまま出力名に採用し、`output/<stem>.md` + `output/<stem>.json` を生成。
- 失敗があっても他ファイルの処理を継続し、成功/失敗サマリを CLI に表示。

## 出力アーティファクト
- `output/<stem>.md`: LangGraph + OpenAI で整形した Markdown。
- `output/<stem>.json`: セクション構成・抽出ナレッジ・関係エッジ・検証結果を含む補助ファイル（RAG のインデックス投入を想定）。

## トラブルシューティング
- `OPENAI_API_KEY` 未設定: CLI が即座にエラー終了します。環境変数を確認してください。
- YAML 形式エラー: エラーメッセージに該当箇所が表示されます。`files` が配列か、`input` が存在するかをご確認ください。
