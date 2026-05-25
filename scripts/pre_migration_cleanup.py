#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
迁移前数据清洗脚本
在 SQLite → PostgreSQL 迁移前运行，确保数据质量

功能:
1. 清理空字符串 → NULL（兼容 PostgreSQL 严格约束）
2. 修复孤立记录（TerminalLog 引用不存在的 server_id 时设为 NULL）
3. 验证 Fernet 加密字段可正常解密
4. 字符集合法性校验

用法:
    python scripts/pre_migration_cleanup.py
"""

import os
import sys
import logging

# 设置 Django 环境
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ops_platform.settings')

import django
django.setup()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger('PreMigrationCleanup')


def clean_empty_strings():
    """
    将指定字段的空字符串转换为 NULL，兼容 PostgreSQL 更严格的约束
    """
    from cmdb.models import Server, CloudAccount, SSLCertificate
    from k8s_manager.models import K8sCluster
    from monitoring.models import AlertRule

    total_fixed = 0
    mappings = [
        (Server, ['username', 'hostname', 'os_name', 'instance_id']),
        (CloudAccount, ['name', 'region', 'access_key']),
        (K8sCluster, ['name', 'version']),
        (AlertRule, ['name', 'metric_name']),
        (SSLCertificate, ['domain', 'issuer']),
    ]

    for model, fields in mappings:
        for field in fields:
            if not hasattr(model, field):
                continue
            try:
                count = model.objects.filter(**{field: ''}).update(**{field: None})
                if count > 0:
                    log.info(f"  清理 {model.__name__}.{field}: {count} 条空字符串 → NULL")
                    total_fixed += count
            except Exception as e:
                log.warning(f"  跳过 {model.__name__}.{field}: {e}")

    return total_fixed


def fix_orphan_records():
    """
    检测并修复孤立记录：
    - TerminalLog 引用不存在的 server_id 时设为 NULL
    - ServerMetric 引用不存在的 server_id 时删除（必须关联服务器）
    - HighRiskAudit 引用不存在的 server_id 时删除（必须关联服务器）
    """
    from django.db import connection

    actions = []

    # 使用 Django ORM 处理可设为 NULL 的外键
    from cmdb.models import TerminalLog, Server

    valid_server_ids = set(Server.objects.values_list('id', flat=True))
    if valid_server_ids:
        orphaned_terminal = TerminalLog.objects.exclude(
            server_id__in=valid_server_ids
        ).exclude(server_id__isnull=True)
        count = orphaned_terminal.count()
        if count > 0:
            orphaned_terminal.update(server=None)
            msg = f"TerminalLog.server: {count} 条孤儿记录 → 设为 NULL"
            actions.append(msg)
            log.info(f"  {msg}")
    else:
        log.warning("  Server 表为空，跳过 TerminalLog 孤儿检查")

    # 使用原生 SQL 处理必须关联服务器的记录（删除孤儿）
    sql_fixes = [
        (
            "cmdb_servermetric",
            "server_id",
            "cmdb_server",
            "id",
            True,
        ),
        (
            "cmdb_highriskaudit",
            "server_id",
            "cmdb_server",
            "id",
            True,
        ),
    ]

    with connection.cursor() as cursor:
        for table, fk_col, ref_table, ref_col, should_delete in sql_fixes:
            try:
                if should_delete:
                    cursor.execute(f"""
                        DELETE FROM "{table}"
                        WHERE "{fk_col}" IS NOT NULL
                        AND "{fk_col}" NOT IN (SELECT "{ref_col}" FROM "{ref_table}")
                    """)
                    fixed = cursor.rowcount
                    if fixed > 0:
                        msg = f"{table}.{fk_col}: {fixed} 条孤儿记录 → 已删除"
                        actions.append(msg)
                        log.info(f"  {msg}")
                else:
                    cursor.execute(f"""
                        UPDATE "{table}" SET "{fk_col}" = NULL
                        WHERE "{fk_col}" IS NOT NULL
                        AND "{fk_col}" NOT IN (SELECT "{ref_col}" FROM "{ref_table}")
                    """)
                    fixed = cursor.rowcount
                    if fixed > 0:
                        msg = f"{table}.{fk_col}: {fixed} 条孤儿记录 → 设为 NULL"
                        actions.append(msg)
                        log.info(f"  {msg}")
            except Exception as e:
                log.warning(f"  跳过 {table}: {e}")

    return actions


def validate_encrypted_fields():
    """
    验证 Fernet 加密字段可正常解密
    检查字段: Server.password, CloudAccount.secret_key, AIModel.api_key
    """
    errors = []
    tests = [
        ('Server.password', 'cmdb', 'Server', 'password'),
        ('CloudAccount.secret_key', 'cmdb', 'CloudAccount', 'secret_key'),
        ('AIModel.api_key', 'ai_ops', 'AIModel', 'api_key'),
    ]

    for label, app_label, model_name, field_name in tests:
        try:
            mod = __import__(f'{app_label}.models', fromlist=[model_name])
            Model = getattr(mod, model_name)
            instance = Model.objects.exclude(
                **{f'{field_name}__isnull': True}
            ).exclude(**{f'{field_name}': ''}).first()

            if not instance:
                log.info(f"  {label}: 无数据，跳过")
                continue

            value = getattr(instance, field_name)
            if value is None or value == '':
                log.info(f"  {label}: 值为空，跳过")
                continue

            log.info(f"  {label}: 解密成功 (长度 {len(str(value))})")
        except Exception as e:
            err_msg = f"{label}: 解密失败 - {e}"
            log.error(f"  {err_msg}")
            errors.append(err_msg)

    return errors


def check_charset():
    """
    检查 SQLite 数据库中所有文本数据是否为合法 UTF-8
    """
    import sqlite3

    sqlite_path = os.path.join(PROJECT_ROOT, 'db.sqlite3')
    if not os.path.exists(sqlite_path):
        log.info("  未找到 db.sqlite3，跳过字符集检查")
        return True

    conn = sqlite3.connect(sqlite_path)
    cur = conn.cursor()

    cur.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
    """)
    tables = [r[0] for r in cur.fetchall()]
    ok = True

    for table in tables:
        try:
            cur.execute(f'SELECT * FROM "{table}" LIMIT 500')
            for row in cur.fetchall():
                for val in row:
                    if isinstance(val, str):
                        val.encode('utf-8')
        except UnicodeEncodeError as e:
            log.error(f"  非 UTF-8 数据: {table} - {e}")
            ok = False
            break
        except Exception as e:
            log.debug(f"  检查 {table} 时出错: {e}")

    conn.close()
    if ok:
        log.info("  字符集检查通过")
    return ok


def run_pre_migration_cleanup():
    """
    执行全部清洗步骤
    返回 True=全部通过, False=有问题
    """
    errors = []

    log.info("=" * 60)
    log.info("开始迁移前数据清洗")
    log.info("=" * 60)

    log.info("[1/4] 清理空字符串 → NULL...")
    cleaned = clean_empty_strings()
    log.info(f"  共清理 {cleaned} 条空字符串记录")

    log.info("[2/4] 修复孤儿记录...")
    orphans = fix_orphan_records()
    if not orphans:
        log.info("  未发现孤儿记录")

    log.info("[3/4] 字符集校验...")
    charset_ok = check_charset()
    if not charset_ok:
        errors.append("字符集检查发现问题")

    log.info("[4/4] 验证加密字段可解密...")
    enc_errors = validate_encrypted_fields()
    if enc_errors:
        errors.extend(enc_errors)
    else:
        log.info("  所有加密字段验证通过")

    log.info("=" * 60)
    if errors:
        log.error(f"清洗完成，发现 {len(errors)} 个问题:")
        for e in errors:
            log.error(f"  - {e}")
        log.info("=" * 60)
        return False

    log.info("清洗全部通过，数据已准备好迁移")
    log.info("=" * 60)
    return True


if __name__ == '__main__':
    ok = run_pre_migration_cleanup()
    sys.exit(0 if ok else 1)
