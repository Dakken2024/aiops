# -*- coding: utf-8 -*-
"""
AiOps 一键迁移执行器
独立运行，不依赖 Django ORM
用法: python run_migration.py [--host localhost] [--port 5432] [--user postgres] [--password 123456]
"""

import os
import sys
import argparse
import logging
import shutil
import time
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger('AiOps-Migrate')

BACKUP_DIR = os.path.join(PROJECT_ROOT, 'backups', f'pre_migration_{datetime.now().strftime("%Y%m%d_%H%M%S")}')


def check_prerequisites():
    """检查前置条件"""
    log.info("=" * 60)
    log.info("🔍 前置条件检查")
    log.info("=" * 60)
    issues = []

    try:
        import psycopg2
        log.info(f"  ✓ psycopg2 已安装: {psycopg2.__version__}")
    except ImportError:
        issues.append("psycopg2 未安装! 请运行: pip install psycopg2-binary==2.9.9")

    sqlite_path = os.path.join(PROJECT_ROOT, 'db.sqlite3')
    if not os.path.exists(sqlite_path):
        issues.append(f"SQLite 文件不存在: {sqlite_path}")
    else:
        size_mb = os.path.getsize(sqlite_path) / (1024*1024)
        log.info(f"  ✓ SQLite 数据库: {size_mb:.1f}MB")

    settings_path = os.path.join(PROJECT_ROOT, 'ops_platform', 'settings.py')
    if not os.path.exists(settings_path):
        issues.append(f"settings.py 不存在: {settings_path}")
    else:
        log.info(f"  ✓ Django settings.py 存在")

    try:
        import django
        log.info(f"  ✓ Django 已安装")
    except ImportError:
        issues.append("Django 未安装!")

    return len(issues) == 0, issues


def step_1_backup():
    """Step 1: 完整数据备份"""
    log.info("\n" + "=" * 60)
    log.info("[Step 1/6] 📦 数据备份")
    log.info("=" * 60)

    import sqlite3
    from .backup import create_full_backup

    result = create_full_backup(PROJECT_ROOT, BACKUP_DIR)
    if result['ok']:
        log.info(f"✅ 备份完成 → {BACKUP_DIR}")
        for f in result.get('files', []):
            log.info(f"   - {f}")
        return True
    else:
        log.error(f"❌ 备份失败: {result.get('error')}")
        return False


def step_2_cleanup():
    """Step 2: 迁移前数据清洗"""
    log.info("\n" + "=" * 60)
    log.info("[Step 2/6] 🧹 数据清洗")
    log.info("=" * 60)

    try:
        from .pre_cleanup import run_pre_migration_cleanup
        ok = run_pre_migration_cleanup()
        if ok:
            log.info("✅ 清洗完成")
            return True
        else:
            log.warning("⚠️ 清洗发现问题 (非致命)")
            return True
    except Exception as e:
        log.warning(f"⚠️ 清洗跳过: {e}")
        return True


def step_3_test_pg(args):
    """Step 3: 测试 PostgreSQL 连接 + 安装扩展"""
    log.info("\n" + "=" * 60)
    log.info("[Step 3/6] 🔌 PostgreSQL 连接测试 & 扩展安装")
    log.info("=" * 60)

    from .db_connections import get_pg_connection, test_pg_connection
    pg_config = {
        'host': args.host, 'port': args.port,
        'user': args.user, 'password': args.password,
        'dbname': args.dbname,
    }

    ok, ver = test_pg_connection(pg_config)
    if not ok:
        log.error(f"❌ PostgreSQL 连接失败: {ver}")
        return False

    log.info(f"✅ PostgreSQL 连接成功: {ver[:60]}...")

    conn = get_pg_connection(pg_config, autocommit=True)
    try:
        from .schema_migration import install_extensions
        install_extensions(conn)
        log.info("✅ 扩展已安装 (vector / pg_trgm / btree_gin)")
    except Exception as e:
        log.warning(f"⚠️ 扩展安装警告: {e}")
    finally:
        conn.close()

    return True


def step_4_schema(args):
    """Step 4: 通过 Django migrate 创建 PG 表结构"""
    log.info("\n" + "=" * 60)
    log.info("[Step 4/6] 🏗️ 创建 PostgreSQL Schema (Django migrate)")
    log.info("=" * 60)

    import subprocess
    env = os.environ.copy()
    env.update({
        'DB_ENGINE': 'postgresql',
        'DB_NAME': args.dbname,
        'DB_USER': args.user,
        'DB_PASSWORD': args.password,
        'DB_HOST': args.host,
        'DB_PORT': str(args.port),
        'PYTHONPATH': PROJECT_ROOT,
    })

    cmd = [sys.executable, os.path.join(PROJECT_ROOT, 'manage.py'),
           'migrate', '--run-syncdb', '--noinput']

    result = subprocess.run(
        cmd, cwd=PROJECT_ROOT,
        capture_output=True, text=True,
        timeout=180, env=env,
    )

    if result.returncode != 0:
        log.error(f"❌ migrate 失败:\n{result.stderr[-1000:] if result.stderr else ''}")
        return False

    log.info(f"✅ Schema 创建完成:\n{result.stdout[-500:]}")
    return True


def step_5_data(args):
    """Step 5: 数据迁移 (SQLite → PostgreSQL)"""
    log.info("\n" + "=" * 60)
    log.info("[Step 5/6] 📊 数据迁移 (SQLite → PostgreSQL)")
    log.info("=" * 60)

    import sqlite3
    from .db_connections import get_sqlite_connection, get_pg_connection
    from .data_migrator import DataMigrator

    sqlite_path = os.path.join(PROJECT_ROOT, 'db.sqlite3')
    pg_config = {
        'host': args.host, 'port': args.port,
        'user': args.user, 'password': args.password,
        'dbname': args.dbname,
    }

    sqlite_conn = get_sqlite_connection(sqlite_path)
    pg_conn = get_pg_connection(pg_config)

    try:
        migrator = DataMigrator(sqlite_conn, pg_conn, log)
        stats = migrator.migrate_all()

        log.info(f"\n📊 迁移统计:")
        log.info(f"   表数量: {stats.get('tables', 0)}")
        log.info(f"   总行数: {stats.get('rows', 0):,}")
        log.info(f"   错误数: {stats.get('errors', 0)}")

        if stats.get('errors', 0) > 0:
            log.warning(f"⚠️ 存在 {stats['errors']} 个表迁移错误，请检查日志")

        return stats.get('errors', 0) == 0
    finally:
        sqlite_conn.close()
        pg_conn.close()


def step_6_validate(args):
    """Step 6: 数据验证"""
    log.info("\n" + "=" * 60)
    log.info("[Step 6/6] ✅ 数据验证")
    log.info("=" * 60)

    from .db_connections import get_pg_connection
    from .validator import MigrationValidator

    pg_config = {
        'host': args.host, 'port': args.port,
        'user': args.user, 'password': args.password,
        'dbname': args.dbname,
    }
    conn = get_pg_connection(pg_config)

    try:
        v = MigrationValidator(conn, log)
        ok = v.run_all()
        return ok
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description='AiOps SQLite→PostgreSQL 一键迁移')
    parser.add_argument('--host', default='localhost', help='PG host')
    parser.add_argument('--port', type=int, default=5432, help='PG port')
    parser.add_argument('--user', default='postgres', help='PG user')
    parser.add_argument('--password', default='123456', help='PG password')
    parser.add_argument('--dbname', default='aiops_db', help='PG database name')
    parser.add_argument('--skip-backup', action='store_true', help='跳过备份')
    parser.add_argument('--step', default='all',
                        choices=['all','backup','cleanup','test','schema','data','validate'])
    args = parser.parse_args()

    log.info("╔══════════════════════════════════════════════════╗")
    log.info("║     AiOps Database Migration Tool v1.0          ║")
    log.info("║     SQLite → PostgreSQL 18 (+PgVector)           ║")
    log.info("╚══════════════════════════════════════════════════╝")
    log.info(f"   Target: postgresql://{args.user}@{args.host}:{args.port}/{args.dbname}")
    log.info(f"   Time:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    ok, issues = check_prerequisites()
    if not ok:
        log.error("❌ 前置条件不满足:")
        for i in issues:
            log.error(f"   - {i}")
        sys.exit(1)

    steps = []
    if args.step == 'all':
        if not args.skip_backup:
            steps.append(('备份', lambda: step_1_backup()))
        steps.extend([
            ('清洗', lambda: step_2_cleanup()),
            ('连接', lambda: step_3_test_pg(args)),
            ('Schema', lambda: step_4_schema(args)),
            ('数据', lambda: step_5_data(args)),
            ('验证', lambda: step_6_validate(args)),
        ])
    else:
        step_map = {
            'backup': lambda: step_1_backup(),
            'cleanup': lambda: step_2_cleanup(),
            'test': lambda: step_3_test_pg(args),
            'schema': lambda: step_4_schema(args),
            'data': lambda: step_5_data(args),
            'validate': lambda: step_6_validate(args),
        }
        steps = [(args.step, step_map[args.step])]

    results = []
    for name, fn in steps:
        t0 = time.time()
        try:
            ok = fn()
            elapsed = time.time() - t0
            status = "✅ PASS" if ok else "❌ FAIL"
            results.append((name, ok))
            log.info(f"\n[{status}] {name} 耗时 {elapsed:.1f}s")
        except Exception as e:
            elapsed = time.time() - t0
            log.error(f"\n[❌ ERROR] {name}: {e} ({elapsed:.1f}s)")
            results.append((name, False))

    log.info("\n" + "=" * 60)
    log.info("🏁 迁移完成汇总:")
    all_pass = True
    for name, ok in results:
        icon = "✅" if ok else "❌"
        log.info(f"  {icon} {name}")
        if not ok:
            all_pass = False

    if all_pass:
        log.info("\n🎉 所有步骤通过! 迁移成功!")
        log.info(f"\n下一步:")
        log.info(f"  1. 设置环境变量 DB_ENGINE=postgresql 后启动应用")
        log.info(f"  2. 或直接运行: set DB_ENGINE=postgresql && python manage.py runserver")
    else:
        log.error("\n⚠️ 部分步骤失败，请查看上方错误信息并修复后重试")

    sys.exit(0 if all_pass else 1)


if __name__ == '__main__':
    main()
