#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
分批导入工具，支持断点续传

功能:
- 读取 Django dumpdata 导出的 JSON 文件
- 按 batch_size（默认 50000）分批导入
- 使用进度文件记录当前进度，支持中断后恢复
- 调用 Django 的 loaddata 命令

用法:
    python scripts/batch_loaddata.py <json_file> [--batch-size 50000] [--progress-file progress.json]

示例:
    python scripts/batch_loaddata.py dumpdata.json
    python scripts/batch_loaddata.py dumpdata.json --batch-size 20000
"""

import os
import sys
import json
import argparse
import logging
import tempfile
import shutil
from datetime import datetime

# 设置 Django 环境
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ops_platform.settings')

import django
django.setup()

from django.core.management import call_command

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger('BatchLoaddata')

DEFAULT_BATCH_SIZE = 50000


def load_progress(progress_file):
    """加载进度文件"""
    if os.path.exists(progress_file):
        try:
            with open(progress_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log.warning(f"读取进度文件失败: {e}，将从头开始")
    return {'last_index': 0, 'total': 0, 'started_at': None, 'completed': False}


def save_progress(progress_file, data):
    """保存进度文件"""
    try:
        with open(progress_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"保存进度文件失败: {e}")


def split_json_data(input_file, batch_size, start_index=0):
    """
    将 JSON 数据分批，返回每批的 (start, end, batch_data)
    支持从指定索引开始
    """
    log.info(f"读取 JSON 文件: {input_file}")
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if not isinstance(data, list):
        log.error("JSON 文件格式错误: 根元素必须是数组")
        return None, 0

    total = len(data)
    log.info(f"总记录数: {total}")

    batches = []
    for i in range(start_index, total, batch_size):
        end = min(i + batch_size, total)
        batches.append((i, end, data[i:end]))

    return batches, total


def import_batch(batch_data, batch_num, temp_dir):
    """
    导入一批数据，使用 Django loaddata 命令
    """
    batch_file = os.path.join(temp_dir, f'batch_{batch_num:04d}.json')
    with open(batch_file, 'w', encoding='utf-8') as f:
        json.dump(batch_data, f, ensure_ascii=False)

    log.info(f"  导入批次 {batch_num} ({len(batch_data)} 条记录)...")
    try:
        call_command('loaddata', batch_file, verbosity=0)
        return True
    except Exception as e:
        log.error(f"  批次 {batch_num} 导入失败: {e}")
        return False


def run_batch_loaddata(input_file, batch_size, progress_file):
    """
    主流程：分批导入，支持断点续传
    """
    progress = load_progress(progress_file)

    if progress.get('completed'):
        log.info("该文件已导入完成，如需重新导入请删除进度文件")
        return True

    if progress.get('started_at') is None:
        progress['started_at'] = datetime.now().isoformat()

    start_index = progress.get('last_index', 0)
    if start_index > 0:
        log.info(f"检测到上次进度，将从第 {start_index} 条记录继续导入")

    batches, total = split_json_data(input_file, batch_size, start_index)
    if batches is None:
        return False

    progress['total'] = total
    save_progress(progress_file, progress)

    temp_dir = tempfile.mkdtemp(prefix='batch_loaddata_')
    log.info(f"临时目录: {temp_dir}")

    try:
        success_count = 0
        fail_count = 0

        for batch_num, (start, end, batch_data) in enumerate(batches, start=1):
            log.info(f"[{start}/{total}] 处理批次 {batch_num}/{len(batches)}")

            ok = import_batch(batch_data, batch_num, temp_dir)
            if ok:
                success_count += 1
                progress['last_index'] = end
                save_progress(progress_file, progress)
            else:
                fail_count += 1
                log.error(f"批次 {batch_num} 失败，停止导入")
                return False

        progress['completed'] = True
        progress['completed_at'] = datetime.now().isoformat()
        save_progress(progress_file, progress)

        log.info("=" * 60)
        log.info(f"导入完成: 成功 {success_count} 批次, 失败 {fail_count} 批次")
        log.info(f"总记录数: {total}")
        log.info("=" * 60)
        return True

    finally:
        try:
            shutil.rmtree(temp_dir)
            log.info(f"已清理临时目录: {temp_dir}")
        except Exception as e:
            log.warning(f"清理临时目录失败: {e}")


def main():
    parser = argparse.ArgumentParser(description='Django 分批导入工具（支持断点续传）')
    parser.add_argument('json_file', help='Django dumpdata 导出的 JSON 文件路径')
    parser.add_argument(
        '--batch-size',
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f'每批导入记录数（默认 {DEFAULT_BATCH_SIZE}）',
    )
    parser.add_argument(
        '--progress-file',
        default=None,
        help='进度文件路径（默认: <json_file>.progress）',
    )
    args = parser.parse_args()

    if not os.path.exists(args.json_file):
        log.error(f"文件不存在: {args.json_file}")
        sys.exit(1)

    progress_file = args.progress_file or f"{args.json_file}.progress"

    log.info("=" * 60)
    log.info("Django 分批导入工具")
    log.info(f"源文件: {args.json_file}")
    log.info(f"批次大小: {args.batch_size}")
    log.info(f"进度文件: {progress_file}")
    log.info("=" * 60)

    ok = run_batch_loaddata(args.json_file, args.batch_size, progress_file)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
