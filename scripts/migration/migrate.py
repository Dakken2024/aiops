# -*- coding: utf-8 -*-
"""
AiOps SQLite → PostgreSQL 18 迁移主程序
支持: 数据备份、Schema创建、数据转换、完整性验证、PgVector扩展
用法: python migrate.py [--step all|backup|schema|data|validate|cleanup] [--pg-host localhost] [--pg-port 5432]
"""

import os
import sys
import argparse
import logging
import shutil
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
BACKUP_DIR = os.path.join(PROJECT_ROOT, 'backups', f'pre_migration_{datetime.now().strftime("%Y%m%d_%H%M%S")}')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger('Migrate')


def setup_django():
    sys.path.insert(0, PROJECT_ROOT)
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ops_platform.settings')
    import django
    django.setup()


def step_backup(args):
    from .backup import create_full_backup
    log.info(f"[Step 1/5] 开始数据备份 → {BACKUP_DIR}")
    result = create_full_backup(PROJECT_ROOT, BACKUP_DIR)
    if result['ok']:
        log.info(f"✅ 备份完成: {result.get('files',[])}")
    else:
        log.error(f"❌ 备份失败: {result.get('error')}")
        sys.exit(1)


def step_cleanup(args):
    from .pre_cleanup import run_pre_migration_cleanup
    log.info("[Step 1.5/5] 执行迁移前数据清洗...")
    ok = run_pre_migration_cleanup()
    if not ok:
        log.error("❌ 数据清洗发现问题，请检查后重试")
        sys.exit(1)
    log.info("✅ 数据清洗完成")


def step_schema(args):
    from .db_connections import get_pg_connection
    from .schema_migration import create_pg_schema, install_extensions
    pg_conn = {
        'host': args.pg_host, 'port': args.pg_port,
        'user': args.pg_user, 'password': args.pg_password,
        'dbname': args.pg_db,
    }
    log.info("[Step 2/5] 连接 PostgreSQL 并安装扩展...")
    conn = get_pg_connection(pg_conn, autocommit=True)
    try:
        install_extensions(conn)
        log.info("✅ PgVector / pg_trgm / btree_gin 扩展已安装")
    except Exception as e:
        log.warning(f"⚠️ 扩展安装警告: {e}")

    log.info("[Step 2.5/5] 创建数据库 Schema (表结构)...")
    try:
        create_pg_schema(conn, PROJECT_ROOT)
        log.info("✅ PostgreSQL 表结构已创建")
    finally:
        conn.close()


def step_data(args):
    from .db_connections import get_sqlite_connection, get_pg_connection
    from .data_migrator import DataMigrator
    sqlite_path = os.path.join(PROJECT_ROOT, 'db.sqlite3')
    pg_conn = {
        'host': args.pg_host, 'port': args.pg_port,
        'user': args.pg_user, 'password': args.pg_password,
        'dbname': args.pg_db,
    }
    log.info("[Step 3/5] 开始数据迁移 (SQLite → PostgreSQL)...")
    sqlite_conn = get_sqlite_connection(sqlite_path)
    pg = get_pg_connection(pg_conn)
    try:
        migrator = DataMigrator(sqlite_conn, pg, log)
        result = migrator.migrate_all()
        log.info(f"✅ 数据迁移完成: {result}")
    finally:
        sqlite_conn.close()
        pg.close()


def step_validate(args):
    from .db_connections import get_pg_connection
    from .validator import MigrationValidator
    pg_conn = {
        'host': args.pg_host, 'port': args.pg_port,
        'user': args.pg_user, 'password': args.pg_password,
        'dbname': args.pg_db,
    }
    log.info("[Step 4/5] 执行迁移后验证...")
    conn = get_pg_connection(pg_conn)
    try:
        v = MigrationValidator(conn, log)
        ok = v.run_all()
        if not ok:
            log.error("❌ 验证未通过，请查看上方错误信息")
            sys.exit(1)
        log.info("🎉 所有验证通过!")
    finally:
        conn.close()


def step_update_settings(args):
    from .settings_updater import update_settings_for_postgres
    settings_path = os.path.join(PROJECT_ROOT, 'ops_platform', 'settings.py')
    log.info("[Step 5/5] 更新 Django settings.py 指向 PostgreSQL...")
    pg_config = {
        'host': args.pg_host, 'port': str(args.pg_port),
        'user': args.pg_user, 'password': args.pg_password,
        'db_name': args.pg_db,
    }
    update_settings_for_postgres(settings_path, pg_config, BACKUP_DIR)
    log.info("✅ settings.py 已更新 (原文件已备份)")


def main():
    parser = argparse.ArgumentParser(description='AiOps SQLite→PostgreSQL Migration Tool')
    parser.add_argument('--step', default='all',
                        choices=['all','backup','cleanup','schema','data','validate','settings'],
                        help='执行步骤: all=全部, 或指定单步')
    parser.add_argument('--pg-host', default='localhost', help='PostgreSQL host')
    parser.add_argument('--pg-port', type=int, default=5432, help='PostgreSQL port')
    parser.add_argument('--pg-user', default='postgres', help='PostgreSQL user')
    parser.add_argument('--pg-password', default='123456', help='PostgreSQL password')
    parser.add_argument('--pg-db', default='aiops_db', help='PostgreSQL database name')
    parser.add_argument('--skip-backup', action='store_true', help='跳过备份(危险!)')
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("🔄 AiOps Database Migration: SQLite → PostgreSQL 18")
    log.info(f"   Target: postgresql://{args.pg_user}@{args.pg_host}:{args.pg_port}/{args.pg_db}")
    log.info("=" * 60)

    steps = {
        'backup': lambda: step_backup(args),
        'cleanup': lambda: step_cleanup(args),
        'schema': lambda: step_schema(args),
        'data': lambda: step_data(args),
        'validate': lambda: step_validate(args),
        'settings': lambda: step_update_settings(args),
    }

    if args.step == 'all':
        order = ['backup','cleanup','schema','data','validate','settings']
        if args.skip_backup:
            order.remove('backup')
        for s in order:
            steps[s]()
    else:
        steps[args.step]()

    log.info("\n" + "=" * 60)
    log.info("🏁 迁移流程执行完毕!")
    log.info("=" * 60)


if __name__ == '__main__':
    main()
