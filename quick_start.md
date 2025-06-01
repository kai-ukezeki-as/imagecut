# 画像分割自動化 - クイックスタートガイド

## 🚀 即座に開始

```bash
# 1. セットアップ（初回のみ）
pip3 install Pillow

# 2. 事前分析
python3 image_splitter.py . --analyze-only

# 3. テスト実行（1つの画像で確認）
python3 image_splitter.py "画像ファイル名.gif" --format instagram_square

# 4. 一括処理
python3 batch_processor.py . --format instagram_square --workers 4
```

## 📊 推奨ワークフロー（1700商品・10,000画像）

### フェーズ1: 準備（5-10分）
```bash
# 分析実行
python3 image_splitter.py 画像フォルダ --analyze-only > 事前分析結果.txt

# 設定確認・調整
# split_config.json を必要に応じて編集
```

### フェーズ2: 自動処理（3-6時間）
```bash
# 大規模一括処理（再開機能付き）
python3 batch_processor.py 画像フォルダ \
    --format instagram_square \
    --workers 4 \
    --resume resume_data.json
```

### フェーズ3: 人間による確認・調整（1-2時間）
- `output/instagram_square/` 内の分割画像を確認
- `batch_processing_report.json` でエラーをチェック
- 必要に応じて手動調整

## ⚡ 処理能力

- **並列処理**: 4コア同時実行
- **処理速度**: 約5-10ファイル/秒
- **10,000画像**: 約30-60分で完了
- **再開機能**: 中断時も安全

## 🎯 最適化のポイント

1. **ワーカー数調整**: CPUコア数の50-75%を推奨
2. **形式選択**: 目的に応じたフォーマットを事前選択
3. **バックアップ**: 元画像のバックアップを事前に作成

## ⚠️ 安全性確保

- ✅ 元画像は自動的に保護される
- ✅ 処理途中で中断・再開可能
- ✅ 詳細ログで全結果を追跡可能
- ✅ エラー時も他の画像処理は継続 