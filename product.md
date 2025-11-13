html2docはローカルに保存してあるhtmlファイルを、langgraphで構成されたAGENTが読み解きRAG入力用のドキュメントに変換するユースケースを想定しています．
対象のhtmlファイルは主にカスタマーサポートのオペレーターの応対マニュアルを想定しており、応対マニュアルは問い合わせ内容に応じて案内が展開される複雑な仕組みを持つものもありますし、表形式のドキュメントの場合もありますし、中には埋め込み画像にドキュメントが記載されていることもあります．
こうした複雑なhtml形式の応対マニュアルを整理された綺麗なmarkdownドキュメントに変換するワークフローを作成いたします．
yamlファイルに対象のhtmlファイルパスを記載し、それをループで順々にmdファイル化していくような使い方を想定しております．

## MVP 要件
- 依存パッケージ管理は `uv`。Python 3.11 以上を想定する。
- CLI コマンドは `html2doc run --config config.yaml` を提供する。`--config` は必須、`--output-dir` は任意（未指定時はリポジトリ直下の `output/`）。
- 変換対象ごとに HTML ファイル名の stem（拡張子除去）をそのまま Markdown ファイル名に利用し、`output/<stem>.md` を生成する。
- OpenAI の `gpt-4.1-mini` を LangGraph 経由で必ず呼び出す。API キーは `OPENAI_API_KEY` から取得し、未設定時は CLI で即座に失敗させる。
- HTML は LLM 入力にそのまま渡しつつ、システムメッセージで Markdown 化ルール（テーブル保持、画像説明、ネスト構造の維持など）を指示する。
- LangGraph で以下 3 ノードを接続した StateGraph を組む：
  1. `load_html`: ファイル内容とメタデータ（ファイルパス、stem）を State に格納。
  2. `convert_to_markdown`: OpenAI API を叩き Markdown を生成。
  3. `persist_markdown`: 出力ディレクトリを作成し、Markdown を保存。
- 処理レポートとして各ファイルの処理結果（成功・失敗、出力パス）を CLI で表示する。

## YAML スキーマ方針
```yaml
model:
  name: gpt-4.1-mini  # 省略時のデフォルト
  temperature: 0.1    # 任意
  top_p: 0.9          # 任意
output:
  dir: output         # 任意。存在しない場合は自動生成
files:
  - input: data/manual_a.html
    title: "Aマニュアル"        # 任意。LangGraph のプロンプトに埋め込む
    context: "VIP顧客向け"      # 任意。追加指示
  - input: data/manual_b.html
```

## LangGraph / LLM 実装メモ
- LangGraph の State は TypedDict で `html`, `metadata`, `markdown` を持つ。
- `convert_to_markdown` ノード内で OpenAI `responses.create` を呼ぶ。Content には system / user それぞれ日本語プロンプトを設定し、HTML 本体は user 側に長文として埋める。
- モデルや温度などのパラメータは YAML の `model` セクションから取得し、未指定時はデフォルト値を採用する。
- 将来的な拡張を見据え、LangGraph の `app.invoke()` を 1 ファイルずつ呼び出す単純実装から開始する。

## 実装状況メモ（2025-11-13）
- `src/html2doc/config.py`: YAML 読み込みとバリデーション。`files[*].input` を絶対パスへ解決し、`output.dir` の指定がなければ設定ファイル直下の `output/` を使う。
- `src/html2doc/llm.py`: `MarkdownGenerator` が `OPENAI_API_KEY` を検証し、ナレッジ抽出 (`extract_knowledge`)、関係推定 (`link_relations`)、Markdown 合成 (`compose_markdown`) を担う。
- `src/html2doc/graph.py`: LangGraph StateGraph で `load_html → parse_html → extract_knowledge → link_relations → compose_markdown → validate_output → persist_markdown` を構築。
- `src/html2doc/runner.py`: 設定ファイルを読み込み、各 HTML を順次 LangGraph に流して結果を収集する。
- `src/html2doc/cli.py`: `html2doc run --config <path>` を提供し、処理結果を色付きで表示する。
- `output/<stem>.json`: Markdown と同時に保存されるナレッジグラフ。セクション構造・アセット・ナレッジ・関係・バリデーション結果を含む。

## エラーハンドリングとログ
- HTML ファイルが存在しない場合はそのファイルのみ失敗として記録し、他のファイル処理は継続する。
- OpenAI API からのエラーは握りつぶさず、メッセージとともに CLI に表示。リトライは MVP 外。
- CLI 実行終了時に成功数・失敗数をサマリ表示する。

## LangGraph 拡張パイプライン案
MVP の 3 ノード（`load_html` → `convert_to_markdown` → `persist_markdown`）をベースに、以下のノードを順次追加しながら RAG 用ナレッジグラフ生成に耐える構成へ進化させる。

1. `parse_html`
   - 目的: BeautifulSoup などで DOM を解析し、タグ階層・テーブル・画像要素を抽出する。
   - 出力: `sections` (List[SectionChunk])、`assets` (画像/添付メタデータ)、`toc` (見出し構造)。
2. `extract_knowledge`
   - 目的: 各 `sections` から「ナレッジユニット」を LLM で JSON 抽出（カテゴリ、手順、前提条件、参照リンク等）。
   - 実装: LangGraph の map ノードで並列化し、`knowledge_items` に蓄積。
3. `link_relations`
   - 目的: `knowledge_items` 間の依存・派生・重複関係を解析し、`relationships` (List[Edge]) を生成。
   - 手法: LLM で GraphRAG 風の構造を組む。必要に応じて類似度検索で補助。
4. `compose_markdown`
   - 目的: 抽出ナレッジ + 関係グラフから章立てを決定し、関連するユニットをまとめて Markdown に整形。
   - 仕様: タイトル、要約、関係性に基づく参照リンクを自動付与。
5. `validate_output`
   - 目的: Markdown の整合性検査（必須セクション、リンク存在、表記揺れなど）。不備があれば `compose_markdown` にフィードバックを返し再実行（LangGraph のループ活用）。
6. `persist_markdown`
   - 目的: 最終 Markdown を保存し、同時に `relationships` などを JSON で書き出して RAG インデックス構築に備える。

### State 拡張イメージ
```python
class DocumentState(TypedDict, total=False):
    metadata: DocumentMetadata
    html: str
    sections: list[SectionChunk]
    assets: list[Asset]
    knowledge_items: list[KnowledgeUnit]
    relationships: list[RelationEdge]
    markdown: str
    report: ValidationReport
```

### 今後の実装優先度
1. `parse_html` + `extract_knowledge` で HTML → ナレッジ単位を明示化する。
2. `link_relations` で応対フロー（前提→対応→フォローアップ）をグラフ化。
3. `compose_markdown` を段階的生成（章ごとに LLM 呼び分け）へ変更し、長文対応と制御性を向上。
4. `validate_output` による自動品質チェックを導入してリトライ可能なワークフローにする。

これにより「ナレッジ同士の関係性を紐解き、関係のある文章を結び付ける」という要件に応じた多段 LangGraph が実現できる。
