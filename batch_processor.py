#!/usr/bin/env python3
"""
大規模画像一括処理ツール
1700商品・10,000画像に対応した自動化スクリプト
"""

import os
import sys
import time
import concurrent.futures
from pathlib import Path
import json
from image_splitter import ImageSplitter
import argparse

class BatchProcessor:
    def __init__(self, max_workers=4, config_file="split_config.json"):
        """
        大規模一括処理用の初期化
        max_workers: 並列処理数（CPUコア数の半分程度を推奨）
        """
        self.splitter = ImageSplitter(config_file)
        self.max_workers = max_workers
        self.results = []
        
    def process_single_image(self, image_path, output_format, output_dir):
        """単一画像の処理（並列処理用）"""
        try:
            result = self.splitter.split_image(image_path, output_format, output_dir)
            result["source_file"] = str(image_path)
            result["timestamp"] = time.time()
            return result
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "source_file": str(image_path),
                "timestamp": time.time()
            }
    
    def process_directory_parallel(self, input_dir, output_format="instagram_square", 
                                 output_dir="output", resume_file=None):
        """
        ディレクトリ内画像の並列処理
        resume_file: 中断時の再開用ファイル
        """
        input_path = Path(input_dir)
        if not input_path.exists():
            raise FileNotFoundError(f"入力ディレクトリが見つかりません: {input_dir}")
        
        # 対応画像形式
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff'}
        
        # 処理対象ファイルリストの作成
        image_files = []
        for image_file in input_path.rglob("*"):  # 再帰的に検索
            if image_file.suffix.lower() in image_extensions:
                image_files.append(image_file)
        
        print(f"処理対象ファイル数: {len(image_files)}")
        
        # 処理済みファイルの確認（再開機能）
        processed_files = set()
        if resume_file and os.path.exists(resume_file):
            with open(resume_file, 'r') as f:
                resume_data = json.load(f)
                processed_files = set(resume_data.get("processed_files", []))
            print(f"再開モード: {len(processed_files)}個のファイルは処理済み")
        
        # 未処理ファイルのフィルタリング
        remaining_files = [f for f in image_files if str(f) not in processed_files]
        print(f"残り処理対象: {len(remaining_files)}個")
        
        if not remaining_files:
            print("すべてのファイルが処理済みです")
            return self.results
        
        # 並列処理の実行
        print(f"並列処理開始（ワーカー数: {self.max_workers}）")
        start_time = time.time()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Future辞書の作成
            future_to_file = {
                executor.submit(self.process_single_image, image_file, output_format, output_dir): image_file
                for image_file in remaining_files
            }
            
            completed = 0
            for future in concurrent.futures.as_completed(future_to_file):
                image_file = future_to_file[future]
                try:
                    result = future.result()
                    self.results.append(result)
                    
                    completed += 1
                    
                    # 進捗表示
                    if completed % 100 == 0 or completed == len(remaining_files):
                        elapsed = time.time() - start_time
                        rate = completed / elapsed if elapsed > 0 else 0
                        remaining = len(remaining_files) - completed
                        eta = remaining / rate if rate > 0 else 0
                        
                        print(f"進捗: {completed}/{len(remaining_files)} "
                              f"({completed/len(remaining_files)*100:.1f}%) "
                              f"処理速度: {rate:.1f}ファイル/秒 "
                              f"残り時間: {eta/60:.1f}分")
                    
                    # 処理済みファイルの記録（再開用）
                    if resume_file:
                        processed_files.add(str(image_file))
                        if completed % 50 == 0:  # 50件ごとに保存
                            self.save_resume_data(resume_file, processed_files)
                    
                    # 成功/失敗の簡易ログ
                    if result.get("success", False):
                        splits = result.get("splits_created", 0)
                        print(f"✓ {image_file.name} → {splits}個に分割")
                    else:
                        print(f"✗ {image_file.name} → エラー: {result.get('error', 'Unknown')}")
                        
                except Exception as e:
                    print(f"✗ {image_file.name} → 例外: {e}")
                    self.results.append({
                        "success": False,
                        "error": str(e),
                        "source_file": str(image_file),
                        "timestamp": time.time()
                    })
        
        # 最終的な再開データの保存
        if resume_file:
            self.save_resume_data(resume_file, processed_files)
        
        total_time = time.time() - start_time
        print(f"\n処理完了: {total_time/60:.1f}分")
        
        return self.results
    
    def save_resume_data(self, resume_file, processed_files):
        """再開用データの保存"""
        resume_data = {
            "timestamp": time.time(),
            "processed_files": list(processed_files),
            "total_processed": len(processed_files)
        }
        with open(resume_file, 'w') as f:
            json.dump(resume_data, f, indent=2)
    
    def generate_detailed_report(self, output_file="batch_processing_report.json"):
        """詳細な処理結果レポートの生成"""
        successful_results = [r for r in self.results if r.get("success", False)]
        failed_results = [r for r in self.results if not r.get("success", False)]
        
        # エラー分析
        error_analysis = {}
        for result in failed_results:
            error = result.get("error", "Unknown")
            error_analysis[error] = error_analysis.get(error, 0) + 1
        
        # 分割数統計
        split_stats = {}
        total_splits = 0
        for result in successful_results:
            splits = result.get("splits_created", 0)
            total_splits += splits
            split_stats[splits] = split_stats.get(splits, 0) + 1
        
        report = {
            "summary": {
                "total_processed": len(self.results),
                "successful": len(successful_results),
                "failed": len(failed_results),
                "success_rate": len(successful_results) / len(self.results) * 100 if self.results else 0,
                "total_splits_created": total_splits
            },
            "error_analysis": error_analysis,
            "split_statistics": split_stats,
            "processing_details": self.results
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        # コンソール出力
        print(f"\n=== 大規模処理結果レポート ===")
        print(f"総処理ファイル数: {report['summary']['total_processed']}")
        print(f"成功: {report['summary']['successful']}")
        print(f"失敗: {report['summary']['failed']}")
        print(f"成功率: {report['summary']['success_rate']:.1f}%")
        print(f"作成された分割画像総数: {report['summary']['total_splits_created']}")
        
        if error_analysis:
            print(f"\n主なエラー:")
            for error, count in sorted(error_analysis.items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"  {error}: {count}件")
        
        print(f"\n詳細レポート: {output_file}")
        
        return report

def main():
    parser = argparse.ArgumentParser(description="大規模画像一括分割処理ツール")
    parser.add_argument("input_dir", help="入力ディレクトリ（再帰的に処理）")
    parser.add_argument("--format", default="instagram_square", 
                       help="出力フォーマット")
    parser.add_argument("--output", default="output", help="出力ディレクトリ")
    parser.add_argument("--workers", type=int, default=4, 
                       help="並列処理数（デフォルト: 4）")
    parser.add_argument("--resume", help="再開用ファイル名")
    parser.add_argument("--config", default="split_config.json", 
                       help="設定ファイルパス")
    
    args = parser.parse_args()
    
    # システム情報の表示
    import multiprocessing
    cpu_count = multiprocessing.cpu_count()
    print(f"システム情報: CPUコア数 {cpu_count}")
    print(f"使用並列処理数: {args.workers}")
    
    if args.workers > cpu_count:
        print(f"警告: 並列処理数がCPUコア数を超えています")
    
    # 処理実行
    processor = BatchProcessor(args.workers, args.config)
    
    try:
        results = processor.process_directory_parallel(
            args.input_dir, 
            args.format, 
            args.output,
            args.resume
        )
        
        # レポート生成
        processor.generate_detailed_report()
        
    except KeyboardInterrupt:
        print("\n\n処理が中断されました")
        if args.resume:
            print(f"再開用データが {args.resume} に保存されています")
            print(f"再開するには: python3 {sys.argv[0]} {args.input_dir} --resume {args.resume}")
        sys.exit(1)
    except Exception as e:
        print(f"エラー: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 