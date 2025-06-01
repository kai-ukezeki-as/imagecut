# 📸 インタラクティブ画像分割ツール - Railway版

LP型画像を意味のある位置で手動分割するWebアプリケーション

## 🚀 Railway公開版について

このアプリケーションはRailway.appでクラウド公開されています。

### ✨ 機能
- **SKU管理**: 商品コード別のファイル整理
- **ドラッグ&ドロップ**: 簡単な画像アップロード
- **インタラクティブ分割**: クリックによる直感的な分割位置指定
- **インライン設定**: 分割エリア上で直接設定変更
- **除外エリア**: 余白部分のスキップ機能
- **サイズサフィックス**: -size拡張子の自動付与
- **ブラウザダウンロード**: 個別・複数選択ダウンロード

### 🛠️ 技術仕様
- **バックエンド**: Python 3.11 + Flask
- **画像処理**: Pillow (PIL)
- **フロントエンド**: Vanilla JavaScript + HTML5/CSS3
- **デプロイ**: Railway + Gunicorn

## 📋 Railway デプロイ手順

### 1. GitHubリポジトリの準備
```bash
# プロジェクトをGitリポジトリに
git init
git add .
git commit -m "Initial commit - Interactive Image Splitter"

# GitHubにプッシュ
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git branch -M main
git push -u origin main
```

### 2. Railwayでの設定
1. [Railway.app](https://railway.app)にアクセス
2. GitHubアカウントでサインイン
3. "New Project" → "Deploy from GitHub repo"
4. 該当リポジトリを選択
5. 自動的にデプロイが開始されます

### 3. 環境変数設定（必要に応じて）
Railway管理画面で以下の環境変数を設定：
- `PORT`: Railway が自動設定（通常設定不要）
- `RAILWAY_ENVIRONMENT`: Railway が自動設定

### 4. カスタムドメイン設定（オプション）
Railway管理画面の "Settings" → "Domains" でカスタムドメインを設定可能

## 📁 ファイル構成

```
.
├── interactive_splitter.py    # メインアプリケーション
├── image_splitter.py          # 画像分割エンジン
├── templates/
│   └── index.html            # WebUI
├── requirements.txt          # Python依存関係
├── Procfile                  # Railway起動設定
├── runtime.txt               # Python バージョン指定
├── railway.toml              # Railway設定
├── nixpacks.toml             # Nixpacks設定
└── README_Railway.md         # このファイル
```

## 🔧 ローカル開発

```bash
# 依存関係インストール
pip install -r requirements.txt

# 開発サーバー起動
python interactive_splitter.py

# ブラウザで http://127.0.0.1:5000 にアクセス
```

## 💡 使用方法

1. **SKU入力**: 商品コード（3文字以上）を入力
2. **画像アップロード**: ドラッグ&ドロップまたはクリックで選択
3. **分割位置指定**: 画像をクリックして分割ライン追加
4. **除外エリア設定**: 余白部分を2クリックで除外指定
5. **セグメント設定**: 各分割エリアで除外・サイズ設定
6. **分割実行**: SKU別フォルダに保存・ダウンロード

## 🎯 特徴

### インライン操作
- 分割エリア内に直接操作コントロールを配置
- 狭い領域でも操作可能な5段階レスポンシブ対応
- スクロール連動で常に操作可能

### 高速処理
- 従来の10-15分 → 15-30秒（20-40倍高速化）
- リアルタイムプレビュー
- ドラッグ可能な分割ライン

### ファイル管理
- SKU別フォルダ自動生成（output/manual_split/SKU/）
- 連番ファイル名（SKU_001.jpg, SKU_002.jpg...）
- サイズサフィックス対応（SKU_001-size.jpg）

## 🚨 注意事項

- Railway無料プランでは月間実行時間に制限あり
- 大容量画像処理時はメモリ使用量に注意
- 一時ファイルは定期的にクリーンアップが必要

## 📞 サポート

- 本アプリケーションは手動分割作業の効率化を目的としています
- 完全自動化ではなく、人間の判断による品質保証が重要です
- 作業効率: 90%自動化達成（残り10%は人間の判断）

## 📜 ライセンス

Private Use Only - 商用利用は事前承認が必要です。 