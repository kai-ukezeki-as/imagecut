#!/usr/bin/env python3
"""
画像自動分割ツール
縦長画像を指定サイズで分割し、各プラットフォーム用に最適化します
"""

import os
import sys
from PIL import Image
import argparse
from pathlib import Path
import json

class ImageSplitter:
    def __init__(self, config_file="split_config.json"):
        """設定ファイルから分割設定を読み込み"""
        self.config = self.load_config(config_file)
        
    def load_config(self, config_file):
        """設定ファイルの読み込み、存在しない場合はデフォルト設定を作成"""
        default_config = {
            "output_formats": {
                "instagram_square": {"width": 1080, "height": 1080},
                "instagram_story": {"width": 1080, "height": 1920},
                "twitter_card": {"width": 1200, "height": 630},
                "facebook_post": {"width": 1200, "height": 630},
                "custom": {"width": 800, "height": 600}
            },
            "overlap_pixels": 0,  # 分割時の重複ピクセル数
            "quality": 95,        # JPEG品質
            "output_format": "JPEG"
        }
        
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            # デフォルト設定ファイルを作成
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2, ensure_ascii=False)
            print(f"設定ファイル {config_file} を作成しました。必要に応じて編集してください。")
            return default_config
    
    def analyze_image(self, image_path):
        """画像を分析し、分割可能性を判定"""
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                file_size = os.path.getsize(image_path)
                
                analysis = {
                    "path": str(image_path),  # PosixPathを文字列に変換
                    "dimensions": (width, height),
                    "file_size_mb": round(file_size / (1024*1024), 2),
                    "aspect_ratio": round(height / width, 2),
                    "is_vertical": height > width,
                    "splits_possible": {}
                }
                
                # 各フォーマットでの分割可能数を計算
                for format_name, dimensions in self.config["output_formats"].items():
                    target_width = dimensions["width"]
                    target_height = dimensions["height"]
                    
                    # 縦長画像の場合、高さ方向の分割数を計算
                    if analysis["is_vertical"]:
                        possible_splits = height // target_height
                        analysis["splits_possible"][format_name] = possible_splits
                
                return analysis
                
        except Exception as e:
            print(f"画像分析エラー {image_path}: {e}")
            return None
    
    def split_image(self, image_path, output_format="instagram_square", output_dir="output"):
        """画像を指定フォーマットで分割"""
        if output_format not in self.config["output_formats"]:
            raise ValueError(f"未対応フォーマット: {output_format}")
        
        target_dims = self.config["output_formats"][output_format]
        target_width = target_dims["width"]
        target_height = target_dims["height"]
        
        # 出力ディレクトリを作成
        output_path = Path(output_dir) / output_format
        output_path.mkdir(parents=True, exist_ok=True)
        
        try:
            with Image.open(image_path) as img:
                img_width, img_height = img.size
                base_name = Path(image_path).stem
                
                # 分割数を計算
                splits = img_height // target_height
                overlap = self.config.get("overlap_pixels", 0)
                
                split_info = []
                
                for i in range(splits):
                    # 切り取り範囲を計算
                    top = i * target_height - (i * overlap)
                    bottom = top + target_height
                    
                    # 画像範囲内に収める
                    if bottom > img_height:
                        bottom = img_height
                        top = bottom - target_height
                    
                    # 切り取り実行
                    crop_box = (0, top, img_width, bottom)
                    cropped = img.crop(crop_box)
                    
                    # GIF等のパレットモードをRGBに変換
                    if cropped.mode in ('P', 'RGBA'):
                        cropped = cropped.convert('RGB')
                    
                    # リサイズ（必要な場合）
                    if cropped.size != (target_width, target_height):
                        cropped = cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)
                    
                    # 保存
                    output_filename = f"{base_name}_{output_format}_{i+1:03d}.jpg"
                    output_file_path = output_path / output_filename
                    
                    cropped.save(
                        output_file_path,
                        format=self.config["output_format"],
                        quality=self.config["quality"],
                        optimize=True
                    )
                    
                    split_info.append({
                        "index": i + 1,
                        "filename": output_filename,
                        "crop_box": crop_box,
                        "output_size": (target_width, target_height)
                    })
                
                return {
                    "success": True,
                    "splits_created": len(split_info),
                    "output_directory": str(output_path),
                    "details": split_info
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def batch_process(self, input_dir, output_format="instagram_square"):
        """ディレクトリ内の全画像を一括処理"""
        input_path = Path(input_dir)
        if not input_path.exists():
            raise FileNotFoundError(f"入力ディレクトリが見つかりません: {input_dir}")
        
        # 対応画像形式
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff'}
        
        results = []
        
        for image_file in input_path.iterdir():
            if image_file.suffix.lower() in image_extensions:
                print(f"処理中: {image_file.name}")
                
                # 分析
                analysis = self.analyze_image(image_file)
                if analysis:
                    print(f"  サイズ: {analysis['dimensions']}")
                    print(f"  分割可能数: {analysis['splits_possible'].get(output_format, 0)}")
                
                # 分割実行
                result = self.split_image(image_file, output_format)
                result["source_file"] = str(image_file)
                result["analysis"] = analysis
                results.append(result)
                
                if result["success"]:
                    print(f"  ✓ {result['splits_created']}個の画像を作成しました")
                else:
                    print(f"  ✗ エラー: {result['error']}")
        
        return results
    
    def generate_report(self, results, output_file="processing_report.json"):
        """処理結果のレポートを生成"""
        report = {
            "total_processed": len(results),
            "successful": len([r for r in results if r.get("success", False)]),
            "failed": len([r for r in results if not r.get("success", False)]),
            "total_splits_created": sum(r.get("splits_created", 0) for r in results),
            "details": results
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\n=== 処理結果レポート ===")
        print(f"処理ファイル数: {report['total_processed']}")
        print(f"成功: {report['successful']}")
        print(f"失敗: {report['failed']}")
        print(f"作成された分割画像数: {report['total_splits_created']}")
        print(f"詳細レポート: {output_file}")
        
        return report

def main():
    parser = argparse.ArgumentParser(description="縦長画像自動分割ツール")
    parser.add_argument("input", help="入力ファイルまたはディレクトリ")
    parser.add_argument("--format", default="instagram_square", 
                       help="出力フォーマット (instagram_square, instagram_story, twitter_card, facebook_post, custom)")
    parser.add_argument("--output", default="output", help="出力ディレクトリ")
    parser.add_argument("--analyze-only", action="store_true", help="分析のみ実行（分割は行わない）")
    parser.add_argument("--config", default="split_config.json", help="設定ファイルパス")
    
    args = parser.parse_args()
    
    splitter = ImageSplitter(args.config)
    
    input_path = Path(args.input)
    
    if args.analyze_only:
        # 分析のみ
        if input_path.is_file():
            analysis = splitter.analyze_image(input_path)
            if analysis:
                print(json.dumps(analysis, indent=2, ensure_ascii=False))
        else:
            # ディレクトリの場合は全ファイルを分析
            image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff'}
            for image_file in input_path.iterdir():
                if image_file.suffix.lower() in image_extensions:
                    analysis = splitter.analyze_image(image_file)
                    if analysis:
                        print(f"\n{image_file.name}:")
                        print(f"  サイズ: {analysis['dimensions']}")
                        print(f"  縦横比: {analysis['aspect_ratio']}")
                        print(f"  分割可能数: {analysis['splits_possible']}")
    else:
        # 実際の分割処理
        if input_path.is_file():
            result = splitter.split_image(input_path, args.format, args.output)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            results = splitter.batch_process(input_path, args.format)
            splitter.generate_report(results)

if __name__ == "__main__":
    main() 