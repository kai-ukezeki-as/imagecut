# 画像自動分割ツール

縦長画像を各プラットフォーム用に自動分割するツールです。

## セットアップ

```bash
# 依存関係のインストール
pip install -r requirements.txt

# ツールを実行可能にする
chmod +x image_splitter.py
```

## 基本的な使用方法

### 1. 画像の分析（実際の分割前の確認）

```bash
# 単一ファイルの分析
python image_splitter.py "3495a26c952c1d8991bc9ddf19b232b5.gif" --analyze-only

# ディレクトリ内全ファイルの分析
python image_splitter.py . --analyze-only
```

### 2. 画像の分割

```bash
# 単一ファイルをInstagram正方形フォーマットで分割
python image_splitter.py "3495a26c952c1d8991bc9ddf19b232b5.gif" --format instagram_square

# ディレクトリ内全ファイルを一括分割
python image_splitter.py . --format instagram_square --output my_output

# 利用可能なフォーマット:
# - instagram_square (1080x1080)
# - instagram_story (1080x1920) 
# - twitter_card (1200x630)
# - facebook_post (1200x630)
# - custom (800x600、設定ファイルで変更可能)
```

## 推奨ワークフロー

### ステップ1: 事前分析
```bash
python image_splitter.py . --analyze-only > analysis_report.txt
```
この結果を確認して、分割数や品質を事前に把握します。

### ステップ2: テスト実行
```bash
# まず1つの画像でテスト
python image_splitter.py "サンプル画像.gif" --format instagram_square
```

### ステップ3: 一括処理
```bash
# 全画像を一括処理
python image_splitter.py . --format instagram_square
```

### ステップ4: 人間による確認・調整
- `output/instagram_square/` ディレクトリ内の分割された画像を確認
- `processing_report.json` で処理結果をレビュー
- 必要に応じて手動で微調整

## 設定のカスタマイズ

`split_config.json` ファイルで以下をカスタマイズできます：

```json
{
  "output_formats": {
    "custom": {"width": 800, "height": 600}
  },
  "overlap_pixels": 0,
  "quality": 95,
  "output_format": "JPEG"
}
```

## 注意点

- 元画像のバックアップを取ってから実行してください
- 大量処理前には必ずテスト実行を行ってください
- 処理後は必ず人間の目で最終確認を行ってください

## エラー対処

- `ModuleNotFoundError: No module named 'PIL'` → `pip install Pillow`
- 権限エラー → `chmod +x image_splitter.py`
- 画像が開けない → ファイル形式やファイル破損を確認 