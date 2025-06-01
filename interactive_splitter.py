#!/usr/bin/env python3
"""
インタラクティブ画像分割ツール
WebUIで人間が切断位置を指定できる画像分割システム
"""

import os
import json
import base64
from pathlib import Path
from PIL import Image
import io
import requests
import uuid
import tempfile
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory

app = Flask(__name__)
app.secret_key = 'imagecut_secret_key_2024'

class InteractiveSplitter:
    def __init__(self):
        self.current_image_path = None
        self.current_image_data = None
        self.current_sku = None
        self.uploaded_images = []
        self.current_image_index = -1
        
    def set_sku(self, sku):
        """SKUを設定"""
        self.current_sku = sku.strip() if sku else None
        
    def add_uploaded_image(self, image_path, original_filename):
        """アップロードされた画像を管理リストに追加"""
        try:
            with Image.open(image_path) as img:
                width, height = img.size
            
            image_info = {
                "path": str(image_path),
                "filename": original_filename,
                "url": f"/uploads/{Path(image_path).name}",
                "size": {"width": width, "height": height}
            }
            
            self.uploaded_images.append(image_info)
            return len(self.uploaded_images) - 1
            
        except Exception as e:
            raise Exception(f"画像の追加に失敗しました: {str(e)}")
    
    def clear_session(self):
        """セッションをクリアし、アップロードされた画像を削除"""
        # アップロードされたファイルを削除
        for image_info in self.uploaded_images:
            try:
                if os.path.exists(image_info["path"]):
                    os.remove(image_info["path"])
            except:
                pass
        
        self.uploaded_images = []
        self.current_image_index = -1
        self.current_image_path = None
        self.current_image_data = None
        
    def download_image_from_url(self, url, filename_prefix="url_image"):
        """URLから画像をダウンロードして一時ファイルとして保存"""
        try:
            # ヘッダーを設定してリクエスト送信
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            # Content-Typeから拡張子を推測
            content_type = response.headers.get('Content-Type', '')
            if 'jpeg' in content_type or 'jpg' in content_type:
                ext = '.jpg'
            elif 'png' in content_type:
                ext = '.png'
            elif 'gif' in content_type:
                ext = '.gif'
            elif 'webp' in content_type:
                ext = '.webp'
            else:
                # URLから拡張子を推測
                url_path = url.split('?')[0]
                if url_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff')):
                    ext = '.' + url_path.split('.')[-1].lower()
                else:
                    ext = '.jpg'
            
            # 一時ファイルを作成
            uploads_dir = Path("uploads")
            uploads_dir.mkdir(exist_ok=True)
            
            # ファイル名を生成
            unique_id = str(uuid.uuid4())[:8]
            filename = f"{filename_prefix}_{unique_id}{ext}"
            temp_path = uploads_dir / filename
            
            # ファイルに保存
            with open(temp_path, 'wb') as f:
                f.write(response.content)
                
            # 画像として読み込み可能かテスト
            with Image.open(temp_path) as img:
                img.verify()
                
            return str(temp_path), filename
            
        except requests.RequestException as e:
            raise Exception(f"URLからの画像取得に失敗しました: {str(e)}")
        except Exception as e:
            raise Exception(f"画像の処理に失敗しました: {str(e)}")
    
    def add_images_from_urls(self, urls):
        """URLリストから画像をダウンロードして追加"""
        results = []
        
        for i, url in enumerate(urls):
            url = url.strip()
            if not url:
                continue
                
            try:
                # URLから画像をダウンロード
                temp_path, filename = self.download_image_from_url(url, f"url_image_{i+1}")
                
                # アップロードされた画像として追加
                image_index = self.add_uploaded_image(temp_path, filename)
                
                results.append({
                    "success": True,
                    "url": url,
                    "filename": filename,
                    "index": image_index
                })
                
            except Exception as e:
                results.append({
                    "success": False,
                    "url": url,
                    "error": str(e)
                })
                
        return results

    def load_image(self, image_path):
        """画像を読み込み、ブラウザ表示用のデータを準備"""
        try:
            with Image.open(image_path) as img:
                # 画像の基本情報
                width, height = img.size
                
                # ブラウザ表示用のサイズ調整（大きすぎる場合）
                display_width = min(width, 800)
                display_height = int(height * (display_width / width))
                
                # ブラウザ表示用画像の作成
                display_img = img.copy()
                if width > 800:
                    display_img = display_img.resize((display_width, display_height), Image.Resampling.LANCZOS)
                
                # Base64エンコード
                buffer = io.BytesIO()
                display_img.save(buffer, format='PNG')
                img_str = base64.b64encode(buffer.getvalue()).decode()
                
                self.current_image_path = image_path
                self.current_image_data = {
                    "path": str(image_path),
                    "original_size": {"width": width, "height": height},
                    "display_size": {"width": display_width, "height": display_height},
                    "base64": img_str,
                    "scale_factor": width / display_width
                }
                
                return self.current_image_data
                
        except Exception as e:
            return {"error": str(e)}
    
    def split_by_positions(self, cut_positions, skip_areas=None, excluded_segments=None, size_segments=None, output_format="custom", output_dir="output"):
        """指定された位置で画像を分割（SKU毎のフォルダに保存、除外エリア考慮、除外セグメント考慮、サイズサフィックス対応）"""
        if not self.current_image_path or not cut_positions:
            return {"error": "画像が読み込まれていないか、カット位置が指定されていません"}
        
        if not self.current_sku:
            return {"error": "SKU（商品コード）が入力されていません"}
        
        if skip_areas is None:
            skip_areas = []
        
        if excluded_segments is None:
            excluded_segments = []
        
        if size_segments is None:
            size_segments = []
        
        try:
            with Image.open(self.current_image_path) as img:
                img_width, img_height = img.size
                base_name = Path(self.current_image_path).stem
                
                # SKU毎の出力ディレクトリを作成
                sku_output_path = Path(output_dir) / "manual_split" / self.current_sku
                sku_output_path.mkdir(parents=True, exist_ok=True)
                
                # カット位置をソートして、分割領域を定義
                sorted_positions = sorted([0] + cut_positions + [img_height])
                
                split_info = []
                segment_index = 1
                excluded_by_segment_count = 0
                
                for i in range(len(sorted_positions) - 1):
                    top = sorted_positions[i]
                    bottom = sorted_positions[i + 1]
                    
                    # セグメント番号による除外チェック
                    if segment_index in excluded_segments:
                        excluded_by_segment_count += 1
                        segment_index += 1
                        continue
                    
                    # 除外エリアと重複チェック
                    is_in_skip_area = False
                    for skip_area in skip_areas:
                        skip_start = skip_area['start']
                        skip_end = skip_area['end']
                        
                        # セグメントが除外エリアと重複している場合
                        if not (bottom <= skip_start or top >= skip_end):
                            is_in_skip_area = True
                            break
                    
                    if is_in_skip_area:
                        # 除外エリアのセグメントはスキップ
                        segment_index += 1
                        continue
                    
                    # 切り取り実行
                    crop_box = (0, top, img_width, bottom)
                    cropped = img.crop(crop_box)
                    
                    # GIF等のパレットモードをRGBに変換
                    if cropped.mode in ('P', 'RGBA'):
                        cropped = cropped.convert('RGB')
                    
                    # サイズサフィックスの確認
                    has_size_suffix = segment_index in size_segments
                    
                    # 通常版を必ず保存
                    output_filename = f"{self.current_sku}_{segment_index:03d}.jpg"
                    output_file_path = sku_output_path / output_filename
                    
                    cropped.save(
                        output_file_path,
                        format="JPEG",
                        quality=95,
                        optimize=True
                    )
                    
                    split_info.append({
                        "index": segment_index,
                        "filename": output_filename,
                        "crop_box": crop_box,
                        "dimensions": (img_width, bottom - top),
                        "size_kb": round(output_file_path.stat().st_size / 1024, 1),
                        "sku": self.current_sku,
                        "has_size_suffix": False,
                        "download_url": f"/download/{self.current_sku}/{output_filename}"
                    })
                    
                    # サイズサフィックス版も保存（該当する場合）
                    if has_size_suffix:
                        size_filename = f"{self.current_sku}_{segment_index:03d}-size.jpg"
                        size_file_path = sku_output_path / size_filename
                        
                        cropped.save(
                            size_file_path,
                            format="JPEG",
                            quality=95,
                            optimize=True
                        )
                        
                        split_info.append({
                            "index": segment_index,
                            "filename": size_filename,
                            "crop_box": crop_box,
                            "dimensions": (img_width, bottom - top),
                            "size_kb": round(size_file_path.stat().st_size / 1024, 1),
                            "sku": self.current_sku,
                            "has_size_suffix": True,
                            "download_url": f"/download/{self.current_sku}/{size_filename}"
                        })
                    
                    segment_index += 1
                
                skipped_count = len([area for area in skip_areas]) if skip_areas else 0
                
                return {
                    "success": True,
                    "splits_created": len(split_info),
                    "skipped_areas": skipped_count,
                    "excluded_segments": excluded_by_segment_count,
                    "output_directory": str(sku_output_path),
                    "sku": self.current_sku,
                    "details": split_info
                }
                
        except Exception as e:
            return {"error": str(e)}

    def batch_process(self, cut_positions, skip_areas=None, excluded_segments=None, size_segments=None, global_numbering=True):
        """全ての画像に対してバッチ処理を実行"""
        if not self.uploaded_images:
            return {"error": "処理する画像がありません"}
        
        if not self.current_sku:
            return {"error": "SKU（商品コード）が入力されていません"}
        
        all_results = []
        total_splits = 0
        global_index = 1
        
        for i, image_info in enumerate(self.uploaded_images):
            # 各画像を順番に処理
            original_path = self.current_image_path
            original_data = self.current_image_data
            original_index = self.current_image_index
            
            try:
                # 画像を読み込み
                self.load_image(image_info['path'])
                
                # 分割処理を実行
                if global_numbering:
                    # グローバル番号付けの場合、segment_indexを調整
                    result = self._split_with_global_numbering(
                        cut_positions, skip_areas, excluded_segments, size_segments, global_index
                    )
                    if "error" not in result:
                        total_splits += result['splits_created']
                        global_index += result['splits_created']
                else:
                    result = self.split_by_positions(cut_positions, skip_areas, excluded_segments, size_segments)
                    if "error" not in result:
                        total_splits += result['splits_created']
                
                all_results.append({
                    "image_filename": image_info['filename'],
                    "image_index": i,
                    "result": result
                })
                
            except Exception as e:
                all_results.append({
                    "image_filename": image_info['filename'],
                    "image_index": i,
                    "result": {"error": str(e)}
                })
            
            # 元の状態に戻す
            self.current_image_path = original_path
            self.current_image_data = original_data
            self.current_image_index = original_index
        
        success_count = len([r for r in all_results if "error" not in r['result']])
        error_count = len(all_results) - success_count
        
        return {
            "success": True,
            "total_images": len(self.uploaded_images),
            "success_count": success_count,
            "error_count": error_count,
            "total_splits_created": total_splits,
            "sku": self.current_sku,
            "results": all_results
        }
    
    def _split_with_global_numbering(self, cut_positions, skip_areas=None, excluded_segments=None, size_segments=None, start_index=1):
        """グローバル番号付けでの分割処理"""
        if not self.current_image_path or not cut_positions:
            return {"error": "画像が読み込まれていないか、カット位置が指定されていません"}
        
        if skip_areas is None:
            skip_areas = []
        
        if excluded_segments is None:
            excluded_segments = []
        
        if size_segments is None:
            size_segments = []
        
        try:
            with Image.open(self.current_image_path) as img:
                img_width, img_height = img.size
                
                # SKU毎の出力ディレクトリを作成
                sku_output_path = Path("output") / "manual_split" / self.current_sku
                sku_output_path.mkdir(parents=True, exist_ok=True)
                
                # カット位置をソートして、分割領域を定義
                sorted_positions = sorted([0] + cut_positions + [img_height])
                
                split_info = []
                segment_index = 1
                global_segment_index = start_index
                excluded_by_segment_count = 0
                
                for i in range(len(sorted_positions) - 1):
                    top = sorted_positions[i]
                    bottom = sorted_positions[i + 1]
                    
                    # セグメント番号による除外チェック
                    if segment_index in excluded_segments:
                        excluded_by_segment_count += 1
                        segment_index += 1
                        continue
                    
                    # 除外エリアと重複チェック
                    is_in_skip_area = False
                    for skip_area in skip_areas:
                        skip_start = skip_area['start']
                        skip_end = skip_area['end']
                        
                        if not (bottom <= skip_start or top >= skip_end):
                            is_in_skip_area = True
                            break
                    
                    if is_in_skip_area:
                        segment_index += 1
                        continue
                    
                    # 切り取り実行
                    crop_box = (0, top, img_width, bottom)
                    cropped = img.crop(crop_box)
                    
                    if cropped.mode in ('P', 'RGBA'):
                        cropped = cropped.convert('RGB')
                    
                    # サイズサフィックスの確認
                    has_size_suffix = segment_index in size_segments
                    
                    # 通常版を保存（グローバル番号使用）
                    output_filename = f"{self.current_sku}_{global_segment_index:03d}.jpg"
                    output_file_path = sku_output_path / output_filename
                    
                    cropped.save(
                        output_file_path,
                        format="JPEG",
                        quality=95,
                        optimize=True
                    )
                    
                    split_info.append({
                        "index": global_segment_index,
                        "filename": output_filename,
                        "crop_box": crop_box,
                        "dimensions": (img_width, bottom - top),
                        "size_kb": round(output_file_path.stat().st_size / 1024, 1),
                        "sku": self.current_sku,
                        "has_size_suffix": False,
                        "download_url": f"/download/{self.current_sku}/{output_filename}"
                    })
                    
                    # サイズサフィックス版も保存（該当する場合）
                    if has_size_suffix:
                        size_filename = f"{self.current_sku}_{global_segment_index:03d}-size.jpg"
                        size_file_path = sku_output_path / size_filename
                        
                        cropped.save(
                            size_file_path,
                            format="JPEG",
                            quality=95,
                            optimize=True
                        )
                        
                        split_info.append({
                            "index": global_segment_index,
                            "filename": size_filename,
                            "crop_box": crop_box,
                            "dimensions": (img_width, bottom - top),
                            "size_kb": round(size_file_path.stat().st_size / 1024, 1),
                            "sku": self.current_sku,
                            "has_size_suffix": True,
                            "download_url": f"/download/{self.current_sku}/{size_filename}"
                        })
                    
                    segment_index += 1
                    global_segment_index += 1
                
                skipped_count = len([area for area in skip_areas]) if skip_areas else 0
                
                return {
                    "success": True,
                    "splits_created": len(split_info),
                    "skipped_areas": skipped_count,
                    "excluded_segments": excluded_by_segment_count,
                    "output_directory": str(sku_output_path),
                    "sku": self.current_sku,
                    "details": split_info
                }
                
        except Exception as e:
            return {"error": str(e)}

# グローバルインスタンス
interactive_splitter = InteractiveSplitter()

@app.route('/')
def index():
    """メインページ"""
    return render_template('index.html')

@app.route('/api/list_images')
def list_images():
    """利用可能な画像ファイル一覧を取得"""
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff'}
    current_dir = Path('.')
    
    images = []
    for file_path in current_dir.iterdir():
        if file_path.suffix.lower() in image_extensions:
            file_size = file_path.stat().st_size
            images.append({
                "name": file_path.name,
                "path": str(file_path),
                "size_mb": round(file_size / (1024*1024), 2)
            })
    
    return jsonify({"images": sorted(images, key=lambda x: x['name'])})

@app.route('/api/load_image', methods=['POST'])
def load_image():
    """画像を読み込み"""
    data = request.get_json()
    image_path = data.get('image_path')
    
    if not image_path or not Path(image_path).exists():
        return jsonify({"error": "画像ファイルが見つかりません"})
    
    result = interactive_splitter.load_image(image_path)
    return jsonify(result)

@app.route('/api/set_sku', methods=['POST'])
def set_sku():
    """SKU（商品コード）を設定"""
    data = request.get_json()
    sku = data.get('sku', '')
    
    if not sku.strip():
        return jsonify({"error": "SKUが入力されていません"})
    
    interactive_splitter.set_sku(sku)
    return jsonify({"success": True, "sku": sku.strip()})

@app.route('/api/upload_image', methods=['POST'])
def upload_image():
    """ドラッグ&ドロップされた画像をアップロード"""
    if 'file' not in request.files:
        return jsonify({"error": "ファイルが選択されていません"})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "ファイル名が空です"})
    
    # 画像ファイルかチェック
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff'}
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in allowed_extensions:
        return jsonify({"error": "サポートされていないファイル形式です"})
    
    try:
        # アップロードディレクトリを作成
        upload_dir = Path("uploads")
        upload_dir.mkdir(exist_ok=True)
        
        # ファイルを保存
        file_path = upload_dir / file.filename
        file.save(str(file_path))
        
        # 画像をアップロード管理に追加
        image_index = interactive_splitter.add_uploaded_image(file_path, file.filename)
        
        # 画像を読み込み
        result = interactive_splitter.load_image(file_path)
        if "error" in result:
            # エラーの場合はアップロードファイルを削除
            file_path.unlink(missing_ok=True)
            return jsonify(result)
        
        # 現在の画像インデックスを設定
        interactive_splitter.current_image_index = image_index
        
        return jsonify({
            "success": True,
            "uploaded_file": str(file_path),
            "image_data": result,
            "image_index": image_index,
            "total_images": len(interactive_splitter.uploaded_images)
        })
        
    except Exception as e:
        return jsonify({"error": f"アップロードに失敗しました: {str(e)}"})

@app.route('/api/upload_from_urls', methods=['POST'])
def upload_from_urls():
    """URLリストから画像をダウンロードしてアップロード"""
    data = request.get_json()
    urls = data.get('urls', [])
    
    if not urls:
        return jsonify({"error": "URLが指定されていません"})
    
    # 改行区切りの文字列の場合は分割
    if isinstance(urls, str):
        urls = [line.strip() for line in urls.split('\n') if line.strip()]
    
    try:
        results = interactive_splitter.add_images_from_urls(urls)
        
        success_count = len([r for r in results if r['success']])
        error_count = len([r for r in results if not r['success']])
        
        # 最初の画像を現在の画像として設定
        if success_count > 0 and interactive_splitter.uploaded_images:
            first_image = interactive_splitter.uploaded_images[0]
            image_result = interactive_splitter.load_image(first_image['path'])
            interactive_splitter.current_image_index = 0
        else:
            image_result = None
        
        return jsonify({
            "success": True,
            "total_urls": len(urls),
            "success_count": success_count,
            "error_count": error_count,
            "results": results,
            "current_image": image_result,
            "total_images": len(interactive_splitter.uploaded_images)
        })
        
    except Exception as e:
        return jsonify({"error": f"URL取得処理に失敗しました: {str(e)}"})

@app.route('/api/navigate_image', methods=['POST'])
def navigate_image():
    """画像間のナビゲーション"""
    data = request.get_json()
    direction = data.get('direction')  # 'next' or 'prev'
    
    if not interactive_splitter.uploaded_images:
        return jsonify({"error": "アップロードされた画像がありません"})
    
    total_images = len(interactive_splitter.uploaded_images)
    current_index = interactive_splitter.current_image_index
    
    if direction == 'next':
        new_index = (current_index + 1) % total_images
    elif direction == 'prev':
        new_index = (current_index - 1) % total_images
    else:
        return jsonify({"error": "無効な方向指定です"})
    
    # 新しい画像を読み込み
    new_image = interactive_splitter.uploaded_images[new_index]
    result = interactive_splitter.load_image(new_image['path'])
    
    if "error" not in result:
        interactive_splitter.current_image_index = new_index
        
        return jsonify({
            "success": True,
            "image_data": result,
            "current_index": new_index,
            "total_images": total_images,
            "filename": new_image['filename']
        })
    else:
        return jsonify(result)

@app.route('/api/clear_session', methods=['POST'])
def clear_session():
    """セッションをクリアし、アップロードされた画像を削除"""
    try:
        interactive_splitter.clear_session()
        return jsonify({"success": True, "message": "セッションをクリアしました"})
    except Exception as e:
        return jsonify({"error": f"セッションクリアに失敗しました: {str(e)}"})

@app.route('/api/upload_multiple', methods=['POST'])
def upload_multiple():
    """複数ファイルのアップロード"""
    if 'files' not in request.files:
        return jsonify({"error": "ファイルが選択されていません"})
    
    files = request.files.getlist('files')
    if not files or len(files) == 0:
        return jsonify({"error": "ファイルが選択されていません"})
    
    # 画像ファイルかチェック
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff'}
    
    upload_results = []
    error_count = 0
    
    try:
        # アップロードディレクトリを作成
        upload_dir = Path("uploads")
        upload_dir.mkdir(exist_ok=True)
        
        for file in files:
            if file.filename == '':
                continue
                
            file_ext = Path(file.filename).suffix.lower()
            if file_ext not in allowed_extensions:
                error_count += 1
                upload_results.append({
                    "filename": file.filename,
                    "success": False,
                    "error": "サポートされていないファイル形式です"
                })
                continue
            
            try:
                # ファイルを保存
                file_path = upload_dir / file.filename
                file.save(str(file_path))
                
                # 画像をアップロード管理に追加
                image_index = interactive_splitter.add_uploaded_image(file_path, file.filename)
                
                upload_results.append({
                    "filename": file.filename,
                    "success": True,
                    "image_index": image_index
                })
                
            except Exception as e:
                error_count += 1
                upload_results.append({
                    "filename": file.filename,
                    "success": False,
                    "error": str(e)
                })
        
        # 最初の画像を現在の画像として設定
        success_count = len([r for r in upload_results if r['success']])
        if success_count > 0 and interactive_splitter.uploaded_images:
            first_image = interactive_splitter.uploaded_images[0]
            image_result = interactive_splitter.load_image(first_image['path'])
            interactive_splitter.current_image_index = 0
        else:
            image_result = None
        
        return jsonify({
            "success": True,
            "total_files": len(files),
            "success_count": success_count,
            "error_count": error_count,
            "results": upload_results,
            "current_image": image_result,
            "total_images": len(interactive_splitter.uploaded_images)
        })
        
    except Exception as e:
        return jsonify({"error": f"アップロード処理に失敗しました: {str(e)}"})

@app.route('/api/split_image', methods=['POST'])
def split_image():
    """指定位置で画像を分割"""
    data = request.get_json()
    cut_positions = data.get('cut_positions', [])
    skip_areas = data.get('skip_areas', [])
    excluded_segments = data.get('excluded_segments', [])
    size_segments = data.get('size_segments', [])
    sku = data.get('sku', '')
    
    # SKUを設定
    if sku.strip():
        interactive_splitter.set_sku(sku)
    
    # ディスプレイ座標を実座標に変換
    if interactive_splitter.current_image_data:
        scale_factor = interactive_splitter.current_image_data['scale_factor']
        actual_positions = [int(pos * scale_factor) for pos in cut_positions]
        
        # 除外エリアも実座標に変換
        actual_skip_areas = []
        for area in skip_areas:
            actual_skip_areas.append({
                'start': int(area['start'] * scale_factor),
                'end': int(area['end'] * scale_factor)
            })
        
        result = interactive_splitter.split_by_positions(actual_positions, actual_skip_areas, excluded_segments, size_segments)
        return jsonify(result)
    
    return jsonify({"error": "画像が読み込まれていません"})

@app.route('/api/batch_split', methods=['POST'])
def batch_split():
    """全ての画像に対してバッチ分割を実行"""
    data = request.get_json()
    cut_positions = data.get('cut_positions', [])
    skip_areas = data.get('skip_areas', [])
    excluded_segments = data.get('excluded_segments', [])
    size_segments = data.get('size_segments', [])
    global_numbering = data.get('global_numbering', True)
    sku = data.get('sku', '')
    
    # SKUを設定
    if sku.strip():
        interactive_splitter.set_sku(sku)
    
    # ディスプレイ座標を実座標に変換
    if interactive_splitter.current_image_data:
        scale_factor = interactive_splitter.current_image_data['scale_factor']
        actual_positions = [int(pos * scale_factor) for pos in cut_positions]
        
        # 除外エリアも実座標に変換
        actual_skip_areas = []
        for area in skip_areas:
            actual_skip_areas.append({
                'start': int(area['start'] * scale_factor),
                'end': int(area['end'] * scale_factor)
            })
        
        result = interactive_splitter.batch_process(
            actual_positions, actual_skip_areas, excluded_segments, size_segments, global_numbering
        )
        return jsonify(result)
    
    return jsonify({"error": "画像が読み込まれていません"})

@app.route('/api/preview_splits', methods=['POST'])
def preview_splits():
    """分割プレビューを生成（除外エリア考慮）"""
    data = request.get_json()
    cut_positions = data.get('cut_positions', [])
    skip_areas = data.get('skip_areas', [])
    
    if not interactive_splitter.current_image_data:
        return jsonify({"error": "画像が読み込まれていません"})
    
    # 分割プレビュー情報を生成
    height = interactive_splitter.current_image_data['display_size']['height']
    sorted_positions = sorted([0] + cut_positions + [height])
    
    preview_segments = []
    segment_index = 1
    
    for i in range(len(sorted_positions) - 1):
        top = sorted_positions[i]
        bottom = sorted_positions[i + 1]
        segment_height = bottom - top
        
        # 最小高さチェックを削除 - どんなに狭くても処理
        
        # 除外エリアと重複チェック
        is_in_skip_area = False
        for skip_area in skip_areas:
            skip_start = skip_area['start']
            skip_end = skip_area['end']
            
            # セグメントが除外エリアと重複している場合
            if not (bottom <= skip_start or top >= skip_end):
                is_in_skip_area = True
                break
        
        if is_in_skip_area:
            # 除外エリアのセグメントはプレビューに含めない
            continue
        
        preview_segments.append({
            "index": segment_index,
            "top": top,
            "height": segment_height,
            "bottom": bottom,
            "is_skipped": False
        })
        
        segment_index += 1
    
    return jsonify({"segments": preview_segments})

@app.route('/output/<path:filename>')
def serve_output(filename):
    """分割された画像ファイルを配信"""
    return send_from_directory('output', filename)

@app.route('/uploads/<filename>')
def serve_uploads(filename):
    """アップロードされた画像ファイルを配信"""
    return send_from_directory('uploads', filename)

@app.route('/download/<sku>/<filename>')
def download_file(sku, filename):
    """個別ファイルのダウンロード"""
    try:
        file_path = Path("output") / "manual_split" / sku / filename
        
        if not file_path.exists():
            return jsonify({"error": "ファイルが見つかりません"}), 404
        
        return send_file(
            str(file_path),
            as_attachment=True,
            download_name=filename,
            mimetype='image/jpeg'
        )
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/download_multiple', methods=['POST'])
def download_multiple():
    """複数ファイルの一括ダウンロード（JavaScript経由）"""
    data = request.get_json()
    file_urls = data.get('file_urls', [])
    
    if not file_urls:
        return jsonify({"error": "ダウンロードするファイルが選択されていません"})
    
    # ファイルパスの検証とBase64エンコード
    file_data = []
    for url in file_urls:
        try:
            # URLからファイルパスを構築
            parts = url.split('/')
            if len(parts) >= 3:
                sku = parts[-2]
                filename = parts[-1]
                file_path = Path("output") / "manual_split" / sku / filename
                
                if file_path.exists():
                    with open(file_path, 'rb') as f:
                        file_content = base64.b64encode(f.read()).decode('utf-8')
                        file_data.append({
                            'filename': filename,
                            'content': file_content,
                            'mime_type': 'image/jpeg'
                        })
        except Exception:
            continue
    
    return jsonify({
        "success": True,
        "files": file_data
    })

def create_templates():
    """HTMLテンプレートを作成"""
    templates_dir = Path("templates")
    templates_dir.mkdir(exist_ok=True)
    
    html_content = '''<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>インタラクティブ画像分割ツール</title>
    <style>
        body {
            font-family: 'Helvetica Neue', Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            text-align: center;
        }
        .content {
            display: flex;
            min-height: 70vh;
        }
        .sidebar {
            width: 300px;
            padding: 20px;
            border-right: 1px solid #eee;
            background: #fafafa;
        }
        .main-area {
            flex: 1;
            padding: 20px;
            position: relative;
        }
        .image-container {
            position: relative;
            border: 2px dashed #ddd;
            border-radius: 8px;
            overflow: hidden;
            margin-bottom: 20px;
        }
        .image-canvas {
            display: block;
            max-width: 100%;
            cursor: crosshair;
        }
        .cut-line {
            position: absolute;
            left: 0;
            right: 0;
            height: 2px;
            background: #ff4757;
            cursor: grab;
            box-shadow: 0 1px 3px rgba(0,0,0,0.3);
            z-index: 10;
        }
        .cut-line:hover {
            background: #ff3742;
            height: 4px;
            cursor: grab;
        }
        .cut-line:active {
            cursor: grabbing;
        }
        .cut-line::before {
            content: '↕️';
            position: absolute;
            left: 50%;
            top: -8px;
            transform: translateX(-50%);
            background: #ff4757;
            color: white;
            font-size: 12px;
            padding: 2px 4px;
            border-radius: 3px;
            opacity: 0;
            transition: opacity 0.2s;
        }
        .cut-line:hover::before {
            opacity: 1;
        }
        .drop-zone-hover {
            border-color: #667eea !important;
            background: #f0f4ff !important;
        }
        .auto-cut-indicator {
            position: absolute;
            right: 10px;
            top: 5px;
            background: rgba(102, 126, 234, 0.8);
            color: white;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 10px;
        }
        .skip-area {
            position: absolute;
            left: 0;
            right: 0;
            background: repeating-linear-gradient(
                45deg,
                rgba(255, 0, 0, 0.1),
                rgba(255, 0, 0, 0.1) 10px,
                rgba(255, 255, 255, 0.1) 10px,
                rgba(255, 255, 255, 0.1) 20px
            );
            border: 2px solid #ff4757;
            border-left: none;
            border-right: none;
            pointer-events: none;
            z-index: 5;
        }
        .skip-area-label {
            position: absolute;
            left: 10px;
            top: 50%;
            transform: translateY(-50%);
            background: rgba(255, 71, 87, 0.9);
            color: white;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
        }
        .segment-preview {
            position: absolute;
            left: 5px;
            right: 5px;
            background: rgba(102, 126, 234, 0.1);
            border: 1px solid rgba(102, 126, 234, 0.3);
            border-radius: 4px;
            pointer-events: none;
        }
        .segment-label {
            position: absolute;
            top: 5px;
            left: 10px;
            background: rgba(102, 126, 234, 0.8);
            color: white;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 12px;
        }
        .segment-controls {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(255, 255, 255, 0.95);
            border: 2px solid #007bff;
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
            pointer-events: auto;
            min-width: 200px;
            text-align: center;
        }
        .segment-controls label {
            display: block;
            margin: 4px 0;
            cursor: pointer;
            font-weight: bold;
        }
        .segment-controls input[type="checkbox"] {
            margin-right: 6px;
            transform: scale(1.2);
        }
        .segment-controls-compact {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(255, 255, 255, 0.95);
            border: 1px solid #007bff;
            border-radius: 4px;
            padding: 4px 6px;
            font-size: 10px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.2);
            pointer-events: auto;
            min-width: 140px;
            text-align: center;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }
        .segment-controls-compact label {
            margin: 0;
            cursor: pointer;
            font-weight: bold;
            white-space: nowrap;
            font-size: 9px;
            display: flex;
            align-items: center;
        }
        .segment-controls-compact input[type="checkbox"] {
            margin-right: 3px;
            transform: scale(0.9);
        }
        .segment-controls-mini {
            position: absolute;
            top: 2px;
            right: 2px;
            background: rgba(255, 255, 255, 0.9);
            border: 1px solid #007bff;
            border-radius: 3px;
            padding: 2px 4px;
            font-size: 8px;
            pointer-events: auto;
            display: flex;
            gap: 4px;
        }
        .segment-controls-mini input[type="checkbox"] {
            transform: scale(0.8);
            margin: 0;
        }
        .segment-controls-mini .mini-label {
            font-size: 8px;
            cursor: pointer;
            color: #007bff;
            font-weight: bold;
        }
        .segment-controls-ultra {
            position: absolute;
            top: 50%;
            left: 100%;
            transform: translateY(-50%);
            background: rgba(255, 255, 255, 0.95);
            border: 2px solid #007bff;
            border-radius: 4px;
            padding: 4px 6px;
            font-size: 9px;
            pointer-events: auto;
            display: flex;
            gap: 6px;
            margin-left: 5px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.2);
            z-index: 15;
            white-space: nowrap;
        }
        .segment-controls-ultra label {
            margin: 0;
            cursor: pointer;
            font-weight: bold;
            display: flex;
            align-items: center;
            color: #007bff;
        }
        .segment-controls-ultra input[type="checkbox"] {
            margin-right: 2px;
            transform: scale(0.9);
        }
        .segment-controls-extreme {
            position: fixed !important;
            background: rgba(255, 255, 255, 0.98) !important;
            border: 3px solid #007bff !important;
            border-radius: 4px !important;
            padding: 4px 8px !important;
            font-size: 10px !important;
            pointer-events: auto !important;
            display: flex !important;
            gap: 4px !important;
            box-shadow: 0 4px 12px rgba(0,0,0,0.4) !important;
            z-index: 99999 !important;
            min-width: 80px !important;
            white-space: nowrap !important;
            visibility: visible !important;
            opacity: 1 !important;
            transform: none !important;
            overflow: visible !important;
        }
        .segment-controls-extreme input[type="checkbox"] {
            transform: scale(0.9) !important;
            margin: 0 !important;
        }
        .segment-controls-extreme .extreme-label {
            font-size: 9px !important;
            cursor: pointer !important;
            display: flex !important;
            align-items: center !important;
            gap: 2px !important;
        }
        .segment-excluded {
            background: repeating-linear-gradient(
                45deg,
                rgba(255, 71, 87, 0.3),
                rgba(255, 71, 87, 0.3) 10px,
                rgba(255, 255, 255, 0.3) 10px,
                rgba(255, 255, 255, 0.3) 20px
            ) !important;
            border: 2px solid #ff4757 !important;
        }
        .segment-size-marked {
            background: rgba(255, 193, 7, 0.2) !important;
            border: 1px solid rgba(255, 193, 7, 0.6) !important;
        }
        .button {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            margin: 5px;
            transition: transform 0.2s;
        }
        .button:hover {
            transform: translateY(-2px);
        }
        .button:disabled {
            background: #ccc;
            cursor: not-allowed;
            transform: none;
        }
        .image-list {
            max-height: 300px;
            overflow-y: auto;
            border: 1px solid #ddd;
            border-radius: 6px;
        }
        .image-item {
            padding: 10px;
            border-bottom: 1px solid #eee;
            cursor: pointer;
            transition: background 0.2s;
        }
        .image-item:hover {
            background: #f0f0f0;
        }
        .image-item.selected {
            background: #e3f2fd;
        }
        .status {
            margin: 10px 0;
            padding: 10px;
            border-radius: 6px;
            font-size: 14px;
        }
        .status.success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .status.error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        .info-panel {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 6px;
            margin: 10px 0;
        }
        .instructions {
            background: #e3f2fd;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 20px;
            line-height: 1.6;
        }
        .mode-selector {
            background: #f8f9fa;
            border: 1px solid #ddd;
            border-radius: 6px;
            padding: 10px;
            margin: 10px 0;
        }
        .mode-button {
            background: #e9ecef;
            border: 1px solid #ced4da;
            padding: 8px 12px;
            margin: 2px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
            transition: all 0.2s;
        }
        .mode-button.active {
            background: #007bff;
            color: white;
            border-color: #007bff;
        }
        .mode-button:hover {
            background: #007bff;
            color: white;
        }
        .segment-controls-extreme {
            position: fixed !important;
            background: rgba(255, 255, 255, 0.98) !important;
            border: 3px solid #007bff !important;
            border-radius: 4px !important;
            padding: 4px 8px !important;
            font-size: 10px !important;
            pointer-events: auto !important;
            display: flex !important;
            gap: 4px !important;
            box-shadow: 0 4px 12px rgba(0,0,0,0.4) !important;
            z-index: 99999 !important;
            min-width: 80px !important;
            white-space: nowrap !important;
            visibility: visible !important;
            opacity: 1 !important;
            transform: none !important;
            overflow: visible !important;
        }
        .segment-controls-extreme input[type="checkbox"] {
            transform: scale(0.9) !important;
            margin: 0 !important;
        }
        .segment-controls-extreme .extreme-label {
            font-size: 9px !important;
            cursor: pointer !important;
            display: flex !important;
            align-items: center !important;
            gap: 2px !important;
        }
        .segment-controls-external {
            position: fixed !important;
            background: rgba(255, 255, 255, 0.98) !important;
            border: 3px solid #007bff !important;
            border-radius: 4px !important;
            padding: 4px 8px !important;
            font-size: 10px !important;
            pointer-events: auto !important;
            display: flex !important;
            gap: 4px !important;
            box-shadow: 0 4px 12px rgba(0,0,0,0.4) !important;
            z-index: 99999 !important;
            min-width: 80px !important;
            white-space: nowrap !important;
            visibility: visible !important;
            opacity: 1 !important;
            transform: none !important;
            overflow: visible !important;
        }
        .segment-controls-external input[type="checkbox"] {
            transform: scale(0.9) !important;
            margin: 0 !important;
        }
        .segment-controls-external .external-label {
            font-size: 9px !important;
            cursor: pointer !important;
            display: flex !important;
            align-items: center !important;
            gap: 2px !important;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🖼️ インタラクティブ画像分割ツール</h1>
            <p>LP型画像を意味のある位置で手動分割</p>
        </div>
        
        <div class="content">
            <div class="sidebar">
                <div class="instructions">
                    <h3>使い方</h3>
                    <ol>
                        <li>SKU（商品コード）を入力</li>
                        <li>画像をドラッグ&ドロップまたは選択</li>
                        <li>画像をクリックしてカット位置を指定</li>
                        <li>各分割エリアのチェックボックスで設定</li>
                        <li>「分割実行」で保存・ダウンロード</li>
                    </ol>
                    <div style="font-size: 11px; color: #666; margin-top: 8px;">
                        💡 分割エリア内で直接除外・サイズ設定が可能
                    </div>
                </div>
                
                <div style="margin-bottom: 20px;">
                    <h3>📦 SKU（商品コード）</h3>
                    <input type="text" id="skuInput" placeholder="例: ABC12345" 
                           style="width: 100%; padding: 10px; border: 2px solid #ddd; border-radius: 6px; font-size: 14px; margin-bottom: 10px;">
                    <div id="skuStatus" style="font-size: 12px; color: #666;"></div>
                </div>
                
                <div style="margin-bottom: 20px;">
                    <h3>🎯 操作モード</h3>
                    <div class="mode-selector">
                        <div class="mode-button active" id="cutMode" onclick="setMode('cut')">
                            ✂️ カット位置指定
                        </div>
                        <div class="mode-button" id="skipMode" onclick="setMode('skip')">
                            🚫 余白除外エリア
                        </div>
                        <div style="font-size: 11px; color: #666; margin-top: 5px;">
                            <span id="modeHelp">画像をクリックしてカット位置を指定</span>
                        </div>
                    </div>
                </div>
                
                <div style="margin-bottom: 20px;">
                    <h3>📁 画像アップロード</h3>
                    <div id="dropZone" style="
                        border: 3px dashed #ddd; 
                        border-radius: 10px; 
                        padding: 30px; 
                        text-align: center; 
                        cursor: pointer;
                        background: #fafafa;
                        transition: all 0.3s ease;
                        margin-bottom: 10px;
                    ">
                        <div id="dropZoneContent">
                            <div style="font-size: 24px; margin-bottom: 10px;">📸</div>
                            <div style="font-weight: bold; margin-bottom: 5px;">画像をドラッグ&ドロップ</div>
                            <div style="font-size: 12px; color: #666;">または クリックして選択</div>
                        </div>
                    </div>
                    <input type="file" id="fileInput" accept="image/*" style="display: none;">
                </div>
                
                <h3>📂 ローカルファイル一覧</h3>
                <div id="imageList" class="image-list">
                    <div style="padding: 20px; text-align: center; color: #999;">
                        読み込み中...
                    </div>
                </div>
                
                <div class="info-panel" id="imageInfo" style="display: none;">
                    <h4>画像情報</h4>
                    <div id="imageDetails"></div>
                </div>
                
                <div style="margin-top: 20px;">
                    <button class="button" id="clearCuts" style="width: 100%;" disabled>
                        🗑️ カット位置をクリア
                    </button>
                    <button class="button" id="clearSkips" style="width: 100%;" disabled>
                        🚫 除外エリアをクリア
                    </button>
                    <button class="button" id="previewBtn" style="width: 100%;" disabled>
                        👁️ プレビュー更新
                    </button>
                    <button class="button" id="splitBtn" style="width: 100%;" disabled>
                        ✂️ 分割実行
                    </button>
                    <div style="font-size: 11px; color: #666; margin-top: 5px; text-align: center;">
                        💡 Deleteキーでカット位置削除
                    </div>
                </div>
                
                <div id="statusArea"></div>
            </div>
            
            <div class="main-area">
                <div id="imageContainer" class="image-container" style="display: none;">
                    <img id="imageCanvas" class="image-canvas" />
                </div>
                
                <div id="noImageMessage" style="text-align: center; color: #999; padding: 50px;">
                    <h2>📁 画像を選択してください</h2>
                    <p>左のリストから画像ファイルを選択すると、ここに表示されます。</p>
                </div>
                
                <!-- ダウンロード結果エリア -->
                <div id="downloadArea" style="display: none; margin-top: 20px; background: #f8f9fa; border-radius: 8px; padding: 20px;">
                    <h3>📥 分割完了 - ダウンロード</h3>
                    <div id="downloadContent">
                        <!-- 分割完了後に動的に生成 -->
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let currentImage = null;
        let cutPositions = [];
        let imageData = null;
        let currentSku = null;
        let skipAreas = []; // 除外エリア（開始Y, 終了Y）
        let isDragging = false;
        let dragIndex = -1;
        let currentMode = 'cut'; // 'cut' または 'skip'
        let skipClickStart = null; // 除外エリア作成時の開始位置
        let sizeSegments = []; // サイズサフィックスを付ける分割番号
        let excludedSegments = []; // 除外する分割番号

        // SKU入力の処理
        function setupSkuInput() {
            const skuInput = document.getElementById('skuInput');
            const skuStatus = document.getElementById('skuStatus');
            
            skuInput.addEventListener('input', function() {
                const sku = this.value.trim();
                
                if (sku.length === 0) {
                    skuStatus.textContent = 'SKUを入力してください';
                    skuStatus.style.color = '#999';
                    currentSku = null;
                } else if (sku.length < 3) {
                    skuStatus.textContent = 'SKUは3文字以上で入力してください';
                    skuStatus.style.color = '#e74c3c';
                    currentSku = null;
                } else {
                    skuStatus.textContent = `✅ SKU: ${sku} (保存先: output/manual_split/${sku}/)`;
                    skuStatus.style.color = '#27ae60';
                    currentSku = sku;
                }
                
                // 分割ボタンの状態を更新
                updateSplitButtonState();
            });
        }
        
        // 分割ボタンの状態を更新
        function updateSplitButtonState() {
            const splitBtn = document.getElementById('splitBtn');
            const canSplit = currentSku && cutPositions.length > 0 && imageData;
            
            splitBtn.disabled = !canSplit;
            
            if (!currentSku) {
                splitBtn.title = 'SKUを入力してください';
            } else if (cutPositions.length === 0) {
                splitBtn.title = 'カット位置を指定してください';
            } else if (!imageData) {
                splitBtn.title = '画像を選択してください';
            } else {
                splitBtn.title = '分割を実行します';
            }
        }

        // 画像リストを読み込み
        async function loadImageList() {
            try {
                const response = await fetch('/api/list_images');
                const data = await response.json();
                
                const listContainer = document.getElementById('imageList');
                listContainer.innerHTML = '';
                
                if (data.images.length === 0) {
                    listContainer.innerHTML = '<div style="padding: 20px; text-align: center; color: #999;">画像ファイルが見つかりません</div>';
                    return;
                }
                
                data.images.forEach(image => {
                    const item = document.createElement('div');
                    item.className = 'image-item';
                    item.innerHTML = `
                        <strong>${image.name}</strong><br>
                        <small>${image.size_mb} MB</small>
                    `;
                    item.onclick = () => selectImage(image, item);
                    listContainer.appendChild(item);
                });
            } catch (error) {
                showStatus('画像リストの読み込みに失敗しました: ' + error.message, 'error');
            }
        }

        // 画像を選択
        async function selectImage(image, element) {
            // 選択状態を更新
            document.querySelectorAll('.image-item').forEach(item => item.classList.remove('selected'));
            element.classList.add('selected');
            
            try {
                const response = await fetch('/api/load_image', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ image_path: image.path })
                });
                
                const data = await response.json();
                
                if (data.error) {
                    showStatus('画像の読み込みに失敗しました: ' + data.error, 'error');
                    return;
                }
                
                imageData = data;
                displayImage(data);
                updateImageInfo(data);
                resetCuts();
                
                showStatus('画像を読み込みました: ' + image.name, 'success');
                
            } catch (error) {
                showStatus('画像の読み込みに失敗しました: ' + error.message, 'error');
            }
        }

        // 画像を表示
        function displayImage(data) {
            const canvas = document.getElementById('imageCanvas');
            const container = document.getElementById('imageContainer');
            const noMessage = document.getElementById('noImageMessage');
            
            canvas.src = 'data:image/png;base64,' + data.base64;
            canvas.onclick = addCutPosition;
            
            container.style.display = 'block';
            noMessage.style.display = 'none';
            
            // ボタンを有効化
            document.getElementById('clearCuts').disabled = false;
            document.getElementById('previewBtn').disabled = false;
            
            // 分割ボタンの状態を更新
            updateSplitButtonState();
        }

        // 画像情報を更新
        function updateImageInfo(data) {
            const infoPanel = document.getElementById('imageInfo');
            const details = document.getElementById('imageDetails');
            
            details.innerHTML = `
                <strong>ファイル:</strong> ${data.path}<br>
                <strong>サイズ:</strong> ${data.original_size.width} × ${data.original_size.height}px<br>
                <strong>表示サイズ:</strong> ${data.display_size.width} × ${data.display_size.height}px
            `;
            
            infoPanel.style.display = 'block';
        }

        // 画像クリック処理
        function addCutPosition(event) {
            // ドラッグ中は無視
            if (isDragging) return;
            
            const rect = event.target.getBoundingClientRect();
            const y = event.clientY - rect.top;
            
            if (currentMode === 'cut') {
                // カット位置追加モード
                const isDuplicate = cutPositions.some(pos => Math.abs(pos - y) < 10);
                if (isDuplicate) return;
                
                cutPositions.push(y);
                cutPositions.sort((a, b) => a - b);
                
                updateCutLines();
                updatePreview();
                updateSplitButtonState();
                
                showStatus(`✂️ カット位置を追加しました (${cutPositions.length}個)`, 'success');
                
            } else if (currentMode === 'skip') {
                // 除外エリア作成モード
                if (skipClickStart === null) {
                    // 1回目のクリック - 開始位置
                    skipClickStart = y;
                    showStatus('🚫 除外エリアの終了位置をクリックしてください', 'success');
                } else {
                    // 2回目のクリック - 終了位置
                    const startY = Math.min(skipClickStart, y);
                    const endY = Math.max(skipClickStart, y);
                    
                    if (endY - startY < 20) {
                        showStatus('除外エリアは20px以上の高さが必要です', 'error');
                        skipClickStart = null;
                        return;
                    }
                    
                    skipAreas.push({start: startY, end: endY});
                    skipClickStart = null;
                    
                    updateSkipAreas();
                    updatePreview();
                    
                    showStatus(`🚫 除外エリアを追加しました (${Math.round(endY - startY)}px)`, 'success');
                }
            }
        }

        // カット線を描画（ドラッグ可能）
        function updateCutLines() {
            // 既存の線を削除
            document.querySelectorAll('.cut-line').forEach(line => line.remove());
            
            const container = document.getElementById('imageContainer');
            
            cutPositions.forEach((y, index) => {
                const line = document.createElement('div');
                line.className = 'cut-line';
                line.style.top = y + 'px';
                line.title = `カット位置 ${index + 1} (ドラッグで移動、右クリックで削除)`;
                line.dataset.index = index;
                
                // ドラッグイベント
                line.addEventListener('mousedown', startDrag);
                line.addEventListener('contextmenu', (e) => {
                    e.preventDefault();
                    removeCutPosition(index);
                });
                
                container.appendChild(line);
            });
        }
        
        // ドラッグ開始
        function startDrag(e) {
            e.preventDefault();
            isDragging = true;
            dragIndex = parseInt(e.target.dataset.index);
            
            document.addEventListener('mousemove', onDrag);
            document.addEventListener('mouseup', endDrag);
            
            e.target.style.cursor = 'grabbing';
        }
        
        // ドラッグ中
        function onDrag(e) {
            if (!isDragging || dragIndex === -1) return;
            
            const container = document.getElementById('imageContainer');
            const rect = container.getBoundingClientRect();
            const y = e.clientY - rect.top;
            
            // 境界チェック
            if (y < 10 || y > container.offsetHeight - 10) return;
            
            // 位置を更新
            cutPositions[dragIndex] = y;
            cutPositions.sort((a, b) => a - b);
            
            // 画面更新
            updateCutLines();
            updatePreview();
        }
        
        // ドラッグ終了
        function endDrag(e) {
            isDragging = false;
            dragIndex = -1;
            
            document.removeEventListener('mousemove', onDrag);
            document.removeEventListener('mouseup', endDrag);
            
            // カーソルを戻す
            document.querySelectorAll('.cut-line').forEach(line => {
                line.style.cursor = 'grab';
            });
            
            showStatus('📍 カット位置を調整しました', 'success');
        }

        // カット位置を削除
        function removeCutPosition(index) {
            cutPositions.splice(index, 1);
            updateCutLines();
            updatePreview();
            updateSplitButtonState();
        }

        // 除外エリアを削除
        function removeSkipArea(index) {
            skipAreas.splice(index, 1);
            updateSkipAreas();
            updatePreview();
            showStatus('🗑️ 除外エリアを削除しました', 'success');
        }

        // プレビューを更新
        async function updatePreview() {
            try {
                const response = await fetch('/api/preview_splits', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ cut_positions: cutPositions, skip_areas: skipAreas })
                });
                
                const data = await response.json();
                
                if (data.error) {
                    showStatus('プレビューの生成に失敗しました: ' + data.error, 'error');
                    return;
                }
                
                // 既存のプレビューを削除
                document.querySelectorAll('.segment-preview').forEach(seg => seg.remove());
                
                const container = document.getElementById('imageContainer');
                
                data.segments.forEach(segment => {
                    const preview = document.createElement('div');
                    preview.className = 'segment-preview';
                    preview.style.top = segment.top + 'px';
                    preview.style.height = segment.height + 'px';
                    preview.dataset.segmentIndex = segment.index;
                    
                    // 除外状態とサイズマーク状態に応じてクラスを追加
                    if (excludedSegments.includes(segment.index)) {
                        preview.classList.add('segment-excluded');
                    }
                    if (sizeSegments.includes(segment.index)) {
                        preview.classList.add('segment-size-marked');
                    }
                    
                    // セグメントラベル
                    const label = document.createElement('div');
                    label.className = 'segment-label';
                    let labelText = `分割 ${segment.index}`;
                    if (excludedSegments.includes(segment.index)) {
                        labelText += ' (除外)';
                    }
                    if (sizeSegments.includes(segment.index)) {
                        labelText += ' (-size)';
                    }
                    label.textContent = labelText;
                    preview.appendChild(label);
                    
                    // インラインコントロール（選択幅に応じて配置方法を決定）
                    const controls = document.createElement('div');
                    
                    // 最初は標準的なコントロールを仮作成してサイズを測定
                    const tempControls = document.createElement('div');
                    tempControls.className = 'segment-controls';
                    tempControls.style.position = 'absolute';
                    tempControls.style.visibility = 'hidden';
                    tempControls.innerHTML = `
                        <div style="margin-bottom: 8px; font-weight: bold; color: #007bff;">
                            分割 ${segment.index}
                        </div>
                        <label>
                            <input type="checkbox">
                            🚫 この分割を除外
                        </label>
                        <label>
                            <input type="checkbox">
                            📏 「-size」サフィックス
                        </label>
                    `;
                    document.body.appendChild(tempControls);
                    const tempRect = tempControls.getBoundingClientRect();
                    const controlsMinHeight = tempRect.height;
                    document.body.removeChild(tempControls);
                    
                    // セグメント高さがコントロールサイズより狭い場合のみ右側配置
                    const needsExternalPlacement = segment.height < controlsMinHeight + 20; // 20pxのマージン
                    
                    if (needsExternalPlacement) {
                        // 狭すぎる場合: 右側に移動（extreme モード）
                        controls.className = 'segment-controls-external';
                        controls.innerHTML = `
                            <label class="external-label">
                                <input type="checkbox" ${excludedSegments.includes(segment.index) ? 'checked' : ''} 
                                       onchange="toggleSegmentExclusion(${segment.index})">
                                🚫
                            </label>
                            <label class="external-label">
                                <input type="checkbox" ${sizeSegments.includes(segment.index) ? 'checked' : ''} 
                                       onchange="toggleSizeSegment(${segment.index})">
                                📏
                            </label>
                        `;
                        
                        // セグメント情報を追加
                        controls.dataset.segmentIndex = segment.index;
                        controls.dataset.isExternal = 'true';
                        
                    } else if (segment.height > 80) {
                        // 十分な高さ: 通常サイズのコントロール
                        controls.className = 'segment-controls';
                        controls.innerHTML = `
                            <div style="margin-bottom: 8px; font-weight: bold; color: #007bff;">
                                分割 ${segment.index}
                            </div>
                            <label>
                                <input type="checkbox" ${excludedSegments.includes(segment.index) ? 'checked' : ''} 
                                       onchange="toggleSegmentExclusion(${segment.index})">
                                🚫 この分割を除外
                            </label>
                            <label>
                                <input type="checkbox" ${sizeSegments.includes(segment.index) ? 'checked' : ''} 
                                       onchange="toggleSizeSegment(${segment.index})">
                                📏 「-size」サフィックス
                            </label>
                        `;
                    } else if (segment.height > 40) {
                        // 中程度の高さ: コンパクトサイズのコントロール  
                        controls.className = 'segment-controls-compact';
                        controls.innerHTML = `
                            <label>
                                <input type="checkbox" ${excludedSegments.includes(segment.index) ? 'checked' : ''} 
                                       onchange="toggleSegmentExclusion(${segment.index})">
                                🚫除外
                            </label>
                            <label>
                                <input type="checkbox" ${sizeSegments.includes(segment.index) ? 'checked' : ''} 
                                       onchange="toggleSizeSegment(${segment.index})">
                                📏-size
                            </label>
                        `;
                    } else {
                        // 狭い高さ: ミニサイズのコントロール
                        controls.className = 'segment-controls-mini';
                        controls.innerHTML = `
                            <label class="mini-label">
                                <input type="checkbox" ${excludedSegments.includes(segment.index) ? 'checked' : ''} 
                                       onchange="toggleSegmentExclusion(${segment.index})">
                                🚫
                            </label>
                            <label class="mini-label">
                                <input type="checkbox" ${sizeSegments.includes(segment.index) ? 'checked' : ''} 
                                       onchange="toggleSizeSegment(${segment.index})">
                                📏
                            </label>
                        `;
                    }
                    
                    // コントロールを追加
                    preview.appendChild(controls);
                    
                    // 外部配置が必要な場合のみ特別処理
                    if (needsExternalPlacement) {
                        setTimeout(() => {
                            positionExternalControls(controls, preview);
                        }, 10);
                    }
                    
                    container.appendChild(preview);
                });
                
            } catch (error) {
                showStatus('プレビューの生成に失敗しました: ' + error.message, 'error');
            }
        }

        // 外部配置コントロールの位置設定
        function positionExternalControls(controls, preview) {
            if (!controls || !preview) return;
            
            // bodyに移動して最前面に
            document.body.appendChild(controls);
            
            updateExternalControlPosition(controls, preview);
            
            // スクロールイベントを監視して位置を更新
            const scrollHandler = () => updateExternalControlPosition(controls, preview);
            const resizeHandler = () => updateExternalControlPosition(controls, preview);
            window.addEventListener('scroll', scrollHandler);
            window.addEventListener('resize', resizeHandler);
            
            // コントロールが削除される際にイベントリスナーも削除
            controls.dataset.scrollHandler = 'attached';
            controls._scrollHandler = scrollHandler;
            controls._resizeHandler = resizeHandler;
        }
        
        // 外部コントロールの位置を更新
        function updateExternalControlPosition(controls, preview) {
            if (!controls || !preview) return;
            
            // 対象セグメントの位置を取得
            const previewRect = preview.getBoundingClientRect();
            const imageContainer = document.getElementById('imageContainer');
            const containerRect = imageContainer.getBoundingClientRect();
            
            // 基本的には画像の右側に配置
            let leftPos = containerRect.right + 10;
            let topPos = previewRect.top + (previewRect.height / 2);
            
            // コントロールサイズを取得
            const controlsRect = controls.getBoundingClientRect();
            
            // 画面右端を超える場合は画像の左側に配置
            if (leftPos + controlsRect.width > window.innerWidth - 10) {
                leftPos = containerRect.left - controlsRect.width - 10;
            }
            
            // それでも画面左端を超える場合は画面内に収める
            if (leftPos < 10) {
                leftPos = 10;
            }
            
            // 縦位置を調整（画面内に収める）
            if (topPos + controlsRect.height > window.innerHeight - 10) {
                topPos = window.innerHeight - controlsRect.height - 10;
            }
            if (topPos < 10) {
                topPos = 10;
            }
            
            // 位置を設定
            controls.style.setProperty('left', leftPos + 'px', 'important');
            controls.style.setProperty('top', topPos + 'px', 'important');
            
            // セグメント番号のラベルを追加（一度だけ）
            if (!controls.querySelector('.segment-number-label')) {
                const segmentLabel = document.createElement('div');
                segmentLabel.className = 'segment-number-label';
                segmentLabel.style.cssText = `
                    position: absolute;
                    top: -8px;
                    left: 50%;
                    transform: translateX(-50%);
                    background: #007bff;
                    color: white;
                    font-size: 8px;
                    padding: 2px 4px;
                    border-radius: 2px;
                    white-space: nowrap;
                `;
                segmentLabel.textContent = `分割${preview.dataset.segmentIndex}`;
                controls.appendChild(segmentLabel);
            }
        }

        // コントロールの強制表示
        function forceShowControls(controls, preview) {
            if (!controls) return;
            
            // 絶対的に表示を保証（より強力な設定）
            controls.style.setProperty('display', 'flex', 'important');
            controls.style.setProperty('visibility', 'visible', 'important');
            controls.style.setProperty('opacity', '1', 'important');
            controls.style.setProperty('pointer-events', 'auto', 'important');
            controls.style.setProperty('position', 'absolute', 'important');
            controls.style.setProperty('z-index', '99999', 'important');
            
            if (controls.classList.contains('segment-controls-extreme')) {
                // 初期スタイル
                controls.style.setProperty('position', 'fixed', 'important');
                controls.style.setProperty('background', 'rgba(255, 255, 255, 0.98)', 'important');
                controls.style.setProperty('border', '3px solid #007bff', 'important');
                controls.style.setProperty('border-radius', '4px', 'important');
                controls.style.setProperty('box-shadow', '0 4px 12px rgba(0,0,0,0.4)', 'important');
                controls.style.setProperty('padding', '4px 8px', 'important');
                controls.style.setProperty('min-width', '80px', 'important');
                controls.style.setProperty('white-space', 'nowrap', 'important');
                
                // 最前面に移動
                document.body.appendChild(controls);
                
                // 対象セグメントの位置を取得
                const previewRect = preview.getBoundingClientRect();
                const controlsRect = controls.getBoundingClientRect();
                
                // 初期位置: 右側に表示
                let leftPos = previewRect.right + 5;
                let topPos = previewRect.top;
                
                // 画面右端を超える場合は左側に表示
                if (leftPos + controlsRect.width > window.innerWidth - 5) {
                    leftPos = previewRect.left - controlsRect.width - 5;
                }
                // それでもはみ出る場合は画面内に収める
                if (leftPos < 5) leftPos = 5;
                
                // 画面下端を超える場合は上に調整
                if (topPos + controlsRect.height > window.innerHeight - 5) {
                    topPos = window.innerHeight - controlsRect.height - 5;
                }
                // 画面上端を超える場合は下に調整
                if (topPos < 5) topPos = 5;
                
                controls.style.setProperty('left', leftPos + 'px', 'important');
                controls.style.setProperty('top', topPos + 'px', 'important');
            }
        }

        // コントロールの位置を調整（画面外にはみ出る場合）
        function adjustControlPosition(controls, preview) {
            if (!controls || !preview) return;
            
            const containerRect = document.getElementById('imageContainer').getBoundingClientRect();
            const controlsRect = controls.getBoundingClientRect();
            
            // 右側にはみ出る場合は左側に配置
            if (controlsRect.right > containerRect.right - 20) {
                if (controls.classList.contains('segment-controls-ultra')) {
                    controls.style.left = 'auto';
                    controls.style.right = '100%';
                    controls.style.marginLeft = '0';
                    controls.style.marginRight = '5px';
                } else if (controls.classList.contains('segment-controls-extreme')) {
                    controls.style.left = 'auto';
                    controls.style.right = '100%';
                    controls.style.marginLeft = '0';
                    controls.style.marginRight = '4px';
                }
            }
            
            // 極端に狭い場合の追加調整
            if (controls.classList.contains('segment-controls-extreme')) {
                // 強制的に表示させる
                controls.style.display = 'flex';
                controls.style.visibility = 'visible';
                controls.style.opacity = '1';
                
                // 上下位置の調整
                const previewRect = preview.getBoundingClientRect();
                if (previewRect.height < 5) {
                    controls.style.top = '-2px';  // 分割エリアの上に配置
                }
            }
        }

        // セグメント除外のトグル
        function toggleSegmentExclusion(segmentIndex) {
            const isExcluded = excludedSegments.includes(segmentIndex);
            
            if (isExcluded) {
                excludedSegments = excludedSegments.filter(index => index !== segmentIndex);
                showStatus(`✅ 分割 ${segmentIndex} の除外を解除しました`, 'success');
            } else {
                excludedSegments.push(segmentIndex);
                excludedSegments.sort((a, b) => a - b);
                showStatus(`🚫 分割 ${segmentIndex} を除外しました`, 'success');
            }
            
            // プレビューを再描画
            updatePreviewVisuals();
        }

        // サイズサフィックスのトグル
        function toggleSizeSegment(segmentIndex) {
            const hasSizeMarker = sizeSegments.includes(segmentIndex);
            
            if (hasSizeMarker) {
                sizeSegments = sizeSegments.filter(index => index !== segmentIndex);
                showStatus(`📏 分割 ${segmentIndex} の「-size」サフィックスを解除しました`, 'success');
            } else {
                sizeSegments.push(segmentIndex);
                sizeSegments.sort((a, b) => a - b);
                showStatus(`📏 分割 ${segmentIndex} に「-size」サフィックスを追加しました`, 'success');
            }
            
            // プレビューを再描画
            updatePreviewVisuals();
        }

        // プレビューの見た目を更新（状態変更時）
        function updatePreviewVisuals() {
            document.querySelectorAll('.segment-preview').forEach(preview => {
                const segmentIndex = parseInt(preview.dataset.segmentIndex);
                
                // クラスをリセット
                preview.classList.remove('segment-excluded', 'segment-size-marked');
                
                // 新しい状態を適用
                if (excludedSegments.includes(segmentIndex)) {
                    preview.classList.add('segment-excluded');
                }
                if (sizeSegments.includes(segmentIndex)) {
                    preview.classList.add('segment-size-marked');
                }
                
                // ラベルを更新
                const label = preview.querySelector('.segment-label');
                if (label) {
                    let labelText = `分割 ${segmentIndex}`;
                    if (excludedSegments.includes(segmentIndex)) {
                        labelText += ' (除外)';
                    }
                    if (sizeSegments.includes(segmentIndex)) {
                        labelText += ' (-size)';
                    }
                    label.textContent = labelText;
                }
                
                // チェックボックスの状態を更新（すべてのコントロールタイプ対応）
                const excludeCheckboxes = preview.querySelectorAll('input[onchange*="toggleSegmentExclusion"]');
                const sizeCheckboxes = preview.querySelectorAll('input[onchange*="toggleSizeSegment"]');
                
                excludeCheckboxes.forEach(checkbox => {
                    checkbox.checked = excludedSegments.includes(segmentIndex);
                });
                
                sizeCheckboxes.forEach(checkbox => {
                    checkbox.checked = sizeSegments.includes(segmentIndex);
                });
            });
            
            // 外部配置されたコントロールも更新
            document.querySelectorAll('.segment-controls-external').forEach(controls => {
                const segmentIndex = parseInt(controls.dataset.segmentIndex);
                
                const excludeCheckboxes = controls.querySelectorAll('input[onchange*="toggleSegmentExclusion"]');
                const sizeCheckboxes = controls.querySelectorAll('input[onchange*="toggleSizeSegment"]');
                
                excludeCheckboxes.forEach(checkbox => {
                    checkbox.checked = excludedSegments.includes(segmentIndex);
                });
                
                sizeCheckboxes.forEach(checkbox => {
                    checkbox.checked = sizeSegments.includes(segmentIndex);
                });
            });
        }

        // 分割を実行
        async function executeSplit() {
            if (!currentSku) {
                showStatus('SKU（商品コード）を入力してください', 'error');
                return;
            }
            
            if (cutPositions.length === 0) {
                showStatus('カット位置を指定してください', 'error');
                return;
            }
            
            try:
                document.getElementById('splitBtn').disabled = true;
                document.getElementById('splitBtn').textContent = '処理中...';
                
                const response = await fetch('/api/split_image', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        cut_positions: cutPositions,
                        skip_areas: skipAreas,
                        excluded_segments: excludedSegments,
                        size_segments: sizeSegments,
                        sku: currentSku
                    })
                });
                
                const data = await response.json();
                
                if (data.error) {
                    showStatus('分割に失敗しました: ' + data.error, 'error');
                } else {
                    let message = `✅ 分割完了！ SKU「${data.sku}」として ${data.splits_created}個のファイルを作成しました。<br>`;
                    if (data.excluded_segments > 0) {
                        message += `🚫 ${data.excluded_segments}個のセグメントを除外しました。<br>`;
                    }
                    if (data.skipped_areas > 0) {
                        message += `🚫 ${data.skipped_areas}個の除外エリアをスキップしました。<br>`;
                    }
                    message += `📁 保存先: ${data.output_directory}`;
                    showStatus(message, 'success');
                    
                    // ダウンロードエリアを表示
                    showDownloadArea(data.details);
                }
                
            except Exception as e:
                showStatus('分割に失敗しました: ' + error.message, 'error');
            finally:
                document.getElementById('splitBtn').disabled = false;
                document.getElementById('splitBtn').textContent = '✂️ 分割実行';
                updateSplitButtonState();
        }

        // ダウンロードエリアを表示
        function showDownloadArea(fileDetails) {
            const downloadArea = document.getElementById('downloadArea');
            const downloadContent = document.getElementById('downloadContent');
            
            let html = `
                <div style="margin-bottom: 15px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                        <div style="font-weight: bold;">📋 分割されたファイル (${fileDetails.length}個)</div>
                        <div>
                            <button onclick="selectAllFiles()" style="background: #28a745; color: white; border: none; padding: 6px 12px; border-radius: 4px; margin-right: 5px; cursor: pointer;">全選択</button>
                            <button onclick="selectNoneFiles()" style="background: #6c757d; color: white; border: none; padding: 6px 12px; border-radius: 4px; margin-right: 10px; cursor: pointer;">選択解除</button>
                            <button onclick="downloadSelected()" style="background: #007bff; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer;">選択したファイルをダウンロード</button>
                        </div>
                    </div>
                    <div style="background: white; border: 1px solid #ddd; border-radius: 6px; max-height: 300px; overflow-y: auto;">
            `;
            
            fileDetails.forEach((file, index) => {
                const sizeLabel = file.has_size_suffix ? ' <span style="background: #ffc107; color: #212529; padding: 2px 6px; border-radius: 3px; font-size: 11px;">-size</span>' : '';
                
                html += `
                    <div style="display: flex; align-items: center; padding: 10px; border-bottom: 1px solid #eee; ${index === fileDetails.length - 1 ? 'border-bottom: none;' : ''}">
                        <input type="checkbox" id="file_${index}" value="${file.download_url}" style="margin-right: 10px; cursor: pointer;">
                        <div style="flex: 1;">
                            <div style="font-weight: bold; margin-bottom: 2px;">
                                ${file.filename}${sizeLabel}
                            </div>
                            <div style="font-size: 12px; color: #666;">
                                ${file.dimensions[0]}×${file.dimensions[1]}px • ${file.size_kb}KB
                            </div>
                        </div>
                        <a href="${file.download_url}" download style="background: #17a2b8; color: white; text-decoration: none; padding: 6px 12px; border-radius: 4px; font-size: 12px;">📥 ダウンロード</a>
                    </div>
                `;
            });
            
            html += `
                    </div>
                </div>
                <div style="font-size: 12px; color: #666; text-align: center; margin-top: 10px;">
                    💡 個別ダウンロードまたは複数選択して一括ダウンロードが可能です
                </div>
            `;
            
            downloadContent.innerHTML = html;
            downloadArea.style.display = 'block';
            
            // スクロールしてダウンロードエリアを表示
            downloadArea.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }

        // ファイル選択操作
        function selectAllFiles() {
            document.querySelectorAll('#downloadContent input[type="checkbox"]').forEach(cb => cb.checked = true);
        }

        function selectNoneFiles() {
            document.querySelectorAll('#downloadContent input[type="checkbox"]').forEach(cb => cb.checked = false);
        }

        // 選択したファイルをダウンロード
        async function downloadSelected() {
            const selectedCheckboxes = document.querySelectorAll('#downloadContent input[type="checkbox"]:checked');
            
            if (selectedCheckboxes.length === 0) {
                showStatus('ダウンロードするファイルを選択してください', 'error');
                return;
            }
            
            // 個別にダウンロードをトリガー
            for (let i = 0; i < selectedCheckboxes.length; i++) {
                const url = selectedCheckboxes[i].value;
                
                // 短い間隔でダウンロード
                setTimeout(() => {
                    const link = document.createElement('a');
                    link.href = url;
                    link.download = '';
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                }, i * 200); // 200ms間隔
            }
            
            showStatus(`📥 ${selectedCheckboxes.length}個のファイルのダウンロードを開始しました`, 'success');
        }

        // カット位置をリセット
        function resetCuts() {
            cutPositions = [];
            sizeSegments = [];
            excludedSegments = [];
            updateCutLines();
            document.querySelectorAll('.segment-preview').forEach(seg => seg.remove());
            
            // 外部配置されたコントロールとスクロールイベントリスナーを削除
            document.querySelectorAll('.segment-controls-external').forEach(ctrl => {
                if (ctrl._scrollHandler) {
                    window.removeEventListener('scroll', ctrl._scrollHandler);
                }
                if (ctrl._resizeHandler) {
                    window.removeEventListener('resize', ctrl._resizeHandler);
                }
                ctrl.remove();
            });
            
            // ダウンロードエリアを非表示
            document.getElementById('downloadArea').style.display = 'none';
            
            updateSplitButtonState();
            showStatus('🗑️ 全てのカット位置をクリアしました', 'success');
        }
        
        // 除外エリアをリセット
        function resetSkips() {
            skipAreas = [];
            skipClickStart = null;
            updateSkipAreas();
            updatePreview();
            showStatus('🚫 全ての除外エリアをクリアしました', 'success');
        }

        // ステータス表示
        function showStatus(message, type) {
            const statusArea = document.getElementById('statusArea');
            statusArea.innerHTML = `<div class="status ${type}">${message}</div>`;
            
            if (type === 'success') {
                setTimeout(() => {
                    statusArea.innerHTML = '';
                }, 5000);
            }
        }

        // イベントリスナー
        document.getElementById('clearCuts').onclick = resetCuts;
        document.getElementById('clearSkips').onclick = resetSkips;
        document.getElementById('previewBtn').onclick = updatePreview;
        document.getElementById('splitBtn').onclick = executeSplit;

        // 初期化
        setupSkuInput();
        setupDropZone();
        setupKeyboardEvents();
        loadImageList();

        // ドラッグ&ドロップ機能のセットアップ
        function setupDropZone() {
            const dropZone = document.getElementById('dropZone');
            const fileInput = document.getElementById('fileInput');
            
            // ドロップゾーンクリックでファイル選択
            dropZone.addEventListener('click', () => {
                fileInput.click();
            });
            
            // ファイル選択時の処理
            fileInput.addEventListener('change', (e) => {
                if (e.target.files.length > 0) {
                    uploadFile(e.target.files[0]);
                }
            });
            
            // ドラッグ&ドロップイベント
            dropZone.addEventListener('dragover', (e) => {
                e.preventDefault();
                dropZone.classList.add('drop-zone-hover');
            });
            
            dropZone.addEventListener('dragleave', (e) => {
                e.preventDefault();
                dropZone.classList.remove('drop-zone-hover');
            });
            
            dropZone.addEventListener('drop', (e) => {
                e.preventDefault();
                dropZone.classList.remove('drop-zone-hover');
                
                const files = e.dataTransfer.files;
                if (files.length > 0) {
                    uploadFile(files[0]);
                }
            });
        }
        
        // ファイルアップロード
        async function uploadFile(file) {
            // 画像ファイルかチェック
            if (!file.type.startsWith('image/')) {
                showStatus('画像ファイルを選択してください', 'error');
                return;
            }
            
            const formData = new FormData();
            formData.append('file', file);
            
            try:
                const dropZone = document.getElementById('dropZone');
                const originalContent = dropZone.innerHTML;
                dropZone.innerHTML = '<div style="color: #667eea;">📤 アップロード中...</div>';
                
                const response = await fetch('/api/upload_image', {
                    method: 'POST',
                    body: formData
                });
                
                const data = await response.json();
                
                if (data.error) {
                    showStatus('アップロードに失敗しました: ' + data.error, 'error');
                    dropZone.innerHTML = originalContent;
                } else:
                    imageData = data.image_data;
                    displayImage(data.image_data);
                    updateImageInfo(data.image_data);
                    resetCuts();
                    
                    showStatus(`✅ アップロード完了: ${file.name}`, 'success');
                    dropZone.innerHTML = `
                        <div style="color: #27ae60;">✅ ${file.name}</div>
                        <div style="font-size: 12px; color: #666; margin-top: 5px;">クリックして別のファイルを選択</div>
                    `;
                }
                
            except Exception as e:
                showStatus('アップロードエラー: ' + error.message, 'error');
                document.getElementById('dropZone').innerHTML = originalContent;
        }

        // モード切り替え
        function setMode(mode) {
            currentMode = mode;
            
            // ボタンの状態更新
            document.querySelectorAll('.mode-button').forEach(btn => btn.classList.remove('active'));
            document.getElementById(mode + 'Mode').classList.add('active');
            
            // ヘルプテキスト更新
            const helpText = mode === 'cut' 
                ? '画像をクリックしてカット位置を指定'
                : '余白の開始位置と終了位置を2回クリックして除外エリアを指定';
            document.getElementById('modeHelp').textContent = helpText;
            
            // カーソルの更新
            const canvas = document.getElementById('imageCanvas');
            if (canvas) {
                canvas.style.cursor = mode === 'cut' ? 'crosshair' : 'pointer';
            }
        }

        // 除外エリアを描画
        function updateSkipAreas() {
            // 既存の除外エリアを削除
            document.querySelectorAll('.skip-area').forEach(area => area.remove());
            
            const container = document.getElementById('imageContainer');
            
            skipAreas.forEach((area, index) => {
                const skipDiv = document.createElement('div');
                skipDiv.className = 'skip-area';
                skipDiv.style.top = area.start + 'px';
                skipDiv.style.height = (area.end - area.start) + 'px';
                
                const label = document.createElement('div');
                label.className = 'skip-area-label';
                label.textContent = `除外 ${index + 1}`;
                skipDiv.appendChild(label);
                
                // 右クリックで削除
                skipDiv.addEventListener('contextmenu', (e) => {
                    e.preventDefault();
                    removeSkipArea(index);
                });
                skipDiv.style.pointerEvents = 'auto';
                
                container.appendChild(skipDiv);
            });
            
            // 除外エリアクリアボタンの状態更新
            document.getElementById('clearSkips').disabled = skipAreas.length === 0;
        }
        
        // キーボードイベント処理
        function setupKeyboardEvents() {
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Delete' || e.key === 'Backspace') {
                    if (cutPositions.length > 0) {
                        // 最後のカット位置を削除
                        cutPositions.pop();
                        updateCutLines();
                        updatePreview();
                        updateSplitButtonState();
                        showStatus('🗑️ 最後のカット位置を削除しました', 'success');
                    }
                }
            });
        }
    </script>
</body>
</html>'''
    
    with open(templates_dir / "index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

def main():
    """メイン関数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="インタラクティブ画像分割ツール")
    parser.add_argument("--host", default="0.0.0.0", help="サーバーホスト")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 5000)), help="サーバーポート")
    parser.add_argument("--debug", action="store_true", help="デバッグモード")
    
    args = parser.parse_args()
    
    # 本番環境判定
    is_production = os.environ.get("RAILWAY_ENVIRONMENT") is not None
    
    # テンプレートファイルを作成
    create_templates()
    
    if not is_production:
        print(f"""
🚀 インタラクティブ画像分割ツールを起動中...

📍 アクセスURL: http://{args.host}:{args.port}
🔧 使い方:
   1. ブラウザで上記URLにアクセス
   2. 画像ファイルを選択
   3. 画像をクリックして分割位置を指定
   4. プレビューで確認後、分割実行

⚠️  終了するには Ctrl+C を押してください
""")
    
    try:
        app.run(host=args.host, port=args.port, debug=args.debug and not is_production)
    except KeyboardInterrupt:
        if not is_production:
            print("\n\n🛑 サーバーを停止しました")

if __name__ == "__main__":
    main() 