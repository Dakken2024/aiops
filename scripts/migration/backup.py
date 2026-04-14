# -*- coding: utf-8 -*-
"""
迁移前数据备份模块
支持: SQLite文件复制、Django JSON导出、Schema快照、校验和生成
"""

import os
import sys
import shutil
import hashlib
import json
from datetime import datetime

log = __import__('logging').getLogger('Migrate.Backup')


def create_full_backup(project_root, backup_dir):
    """
    执行完整备份:
    1. SQLite 文件复制
    2. Django dumpdata JSON 导出
    3. Schema 快照 (SQL)
    4. 校验和生成
    """
    results = {'ok': True, 'files': [], 'errors': []}

    os.makedirs(backup_dir, exist_ok=True)
    log.info(f"备份目录: {backup_dir}")

    sqlite_path = os.path.join(project_root, 'db.sqlite3')

    if not os.path.exists(sqlite_path):
        results['ok'] = False
        results['error'] = f'SQLite 文件不存在: {sqlite_path}'
        return results

    try:
        backup_sqlite = os.path.join(backup_dir, 'db.sqlite3.backup')
        shutil.copy2(sqlite_path, backup_sqlite)
        size_mb = os.path.getsize(backup_sqlite) / (1024 * 1024)
        results['files'].append(f'db.sqlite3.backup ({size_mb:.1f}MB)')
        log.info(f"  ✓ SQLite 文件备份: {size_mb:.1f}MB")
    except Exception as e:
        results['errors'].append(f'SQLite 备份失败: {e}')
        log.error(f"  ✗ SQLite 备份失败: {e}")

    try:
        export_django_data(project_root, backup_dir)
        results['files'].append('django_export.json')
        log.info("  ✓ Django 数据导出完成")
    except Exception as e:
        results['errors'].append(f'Django 导出失败: {e}')
        log.warning(f"  ⚠ Django 导出失败: {e} (非致命)")

    try:
        schema_path = export_schema_snapshot(sqlite_path, backup_dir)
        results['files'].append('sqlite_schema.sql')
        log.info("  ✓ Schema 快照完成")
    except Exception as e:
        results['errors'].append(f'Schema 导出失败: {e}')

    try:
        checksum_file = generate_checksums(backup_dir)
        results['files'].append('checksums.sha256')
        log.info("  ✓ 校验和生成完成")
    except Exception as e:
        results['errors'].append(f'校验和生成失败: {e}')

    if len(results['errors']) > 2:
        results['ok'] = False
        results['error'] = f"多个备份步骤失败: {results['errors']}"

    return results


def export_django_data(project_root, backup_dir):
    """使用 Django manage.py dumpdata 导出数据"""
    import subprocess
    output_path = os.path.join(backup_dir, 'django_export.json')

    apps = ['system', 'cmdb', 'k8s_manager', 'script_manager',
            'ai_ops', 'monitoring', 'auth', 'contenttypes',
            'sessions', 'admin']

    cmd = [
        sys.executable, 'manage.py', 'dumpdata',
        '--natural-foreign', '--natural-primary',
        '--indent', '2',
    ] + apps

    env = os.environ.copy()
    env['PYTHONPATH'] = project_root
    env['DJANGO_SETTINGS_MODULE'] = 'ops_platform.settings'

    result = subprocess.run(
        cmd, cwd=project_root,
        capture_output=True, text=True,
        timeout=300, env=env,
    )

    if result.returncode != 0:
        raise RuntimeError(f"dumpdata 失败: {result.stderr[:500]}")

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(result.stdout)

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    log.info(f"    Django 导出: {len(result.stdout)} 字符 ({size_mb:.1f}MB)")


def export_schema_snapshot(sqlite_path, backup_dir):
    """导出 SQLite 表结构 SQL"""
    import sqlite3
    conn = sqlite3.connect(sqlite_path)
    cur = conn.cursor()

    schema_path = os.path.join(backup_dir, 'sqlite_schema.sql')
    with open(schema_path, 'w', encoding='utf-8') as f:
        cur.execute("SELECT sql FROM sqlite_master WHERE type IN ('table','index') AND name NOT LIKE 'sqlite_%'")
        for row in cur.fetchall():
            if row[0]:
                f.write(row[0])
                f.write(';\n\n')

        f.write('-- === Table Statistics ===\n')
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
        for (table,) in cur.fetchall():
            cur.execute(f'SELECT COUNT(*) FROM "{table}"')
            count = cur.fetchone()[0]
            f.write(f"-- {table}: {count} rows\n")

    conn.close()
    return schema_path


def generate_checksums(backup_dir):
    """为所有备份文件生成 SHA256 校验和"""
    checksum_path = os.path.join(backup_dir, 'checksums.sha256')
    hashes = []

    for fname in sorted(os.listdir(backup_dir)):
        fpath = os.path.join(backup_dir, fname)
        if os.path.isfile(fpath):
            sha256 = _file_sha256(fpath)
            hashes.append(f"{sha256}  {fname}")

    with open(checksum_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(hashes))
        f.write('\n')

    return checksum_path


def _file_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def verify_backup(backup_dir):
    """验证备份完整性"""
    checksum_path = os.path.join(backup_dir, 'checksums.sha256')
    if not os.path.exists(checksum_path):
        return False, "缺少校验和文件"

    errors = []
    with open(checksum_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('  ', 1)
            if len(parts) == 2:
                expected, fname = parts
                actual = _file_sha256(os.path.join(backup_dir, fname))
                if expected != actual:
                    errors.append(f"{fname}: 校验和不匹配")

    if errors:
        return False, errors
    return True, "所有文件校验通过"
