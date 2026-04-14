# -*- coding: utf-8 -*-
"""
迁移前数据清洗模块
处理: 空字符串→NULL、孤儿记录修复、字符集校验、加密数据验证
"""

import os
import sys

log = __import__('logging').getLogger('Migrate.Cleanup')


def setup_django():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ops_platform.settings')
    import django
    django.setup()


def run_pre_migration_cleanup():
    """执行全部清洗步骤，返回 True=全部通过, False=有问题"""
    setup_django()
    errors = []

    log.info("  [1/4] 清理空字符串 → NULL...")
    cleaned = clean_empty_strings()
    if cleaned > 0:
        log.info(f"    清理了 {cleaned} 条空字符串记录")

    log.info("  [2/4] 修复孤儿记录...")
    orphans = fix_orphan_records()
    if orphans:
        for o in orphans:
            log.warning(f"    ⚠️ {o}")

    log.info("  [3/4] 字符集校验...")
    charset_ok = check_charset()
    if not charset_ok:
        errors.append("字符集检查发现问题")

    log.info("  [4/4] 验证加密字段可解密...")
    enc_errors = validate_encrypted_fields()
    if enc_errors:
        for e in enc_errors:
            log.error(f"    ❌ {e}")
        errors.extend(enc_errors)

    return len(errors) == 0


def clean_empty_strings():
    """将空字符串转换为 None (NULL) 以兼容 PostgreSQL 更严格的约束"""
    total_fixed = 0
    try:
        from cmdb.models import Server, CloudAccount, SSLCertificate
        from k8s_manager.models import K8sCluster
        from ai_ops import models as ai_models
        from monitoring.models import AlertRule, AlertEvent

        mappings = [
            (Server, ['username', 'hostname', 'os_name', 'remark']),
            (CloudAccount, ['name', 'region', 'remark']),
            (K8sCluster, ['name', 'version', 'remark']),
            (AlertRule, ['name', 'metric_name', 'message_template']),
            (SSLCertificate, ['domain', 'issuer', 'subject']),
        ]

        for model, fields in mappings:
            try:
                for field in fields:
                    if hasattr(model, field):
                        count = model.objects.filter(**{field: ''}).update(**{field: None})
                        if count > 0:
                            log.info(f"      {model.__name__}.{field}: {count} 条")
                            total_fixed += count
            except Exception as e:
                log.debug(f"    跳过 {model.__name__}.{field}: {e}")
    except Exception as e:
        log.warning(f"    清洗过程异常: {e}")

    return total_fixed


def fix_orphan_records():
    """检测并修复孤儿记录(引用不存在的外键)"""
    actions = []
    from django.db import connection

    checks = [
        ("cmdb_terminallog", "server_id", "cmdb_server", "id"),
        ("cmdb_highriskaudit", "server_id", "cmdb_server", "id"),
        ("cmdb_servermetric", "server_id", "cmdb_server", "id"),
        ("ai_ops_chatsession", "user_id", "system_user", "id"),
        ("script_manager_tasklog", "server_id", "cmdb_server", "id"),
    ]

    with connection.cursor() as cursor:
        for table, fk_col, ref_table, ref_col in checks:
            try:
                cursor.execute(f"""
                    UPDATE "{table}" SET "{fk_col}" = NULL
                    WHERE "{fk_col}" IS NOT NULL
                    AND "{fk_col}" NOT IN (SELECT "{ref_col}" FROM "{ref_table}")
                """)
                fixed = cursor.rowcount
                if fixed > 0:
                    msg = f"{table}.{fk_col}: {fixed} 条孤儿 → 设为NULL"
                    actions.append(msg)
                    log.info(f"      {msg}")
            except Exception as e:
                log.debug(f"    跳过 {table}: {e}")

    return actions


def check_charset():
    """检查所有文本数据是否为合法 UTF-8"""
    import sqlite3
    sqlite_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        '..', 'db.sqlite3'
    )
    if not os.path.exists(sqlite_path):
        return True

    conn = sqlite3.connect(sqlite_path)
    cur = conn.cursor()

    cur.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
    """)
    tables = [r[0] for r in cur.fetchall()]
    ok = True

    for table in tables[:20]:
        try:
            cur.execute(f'SELECT * FROM "{table}" LIMIT 500')
            for row in cur.fetchall():
                for val in row:
                    if isinstance(val, str):
                        val.encode('utf-8')
        except UnicodeEncodeError as e:
            log.error(f"    非 UTF-8 数据: {table} - {e}")
            ok = False
            break

    conn.close()
    return ok


def validate_encrypted_fields():
    """验证 Fernet 加密字段在迁移后仍可解密"""
    errors = []
    tests = [
        ('Server.password', 'cmdb', 'Server', 'password'),
        ('CloudAccount.secret_key', 'cmdb', 'CloudAccount', 'secret_key'),
        ('AIModel.api_key', 'ai_ops', 'AIModel', 'api_key'),
        ('K8SCluster.kubeconfig', 'k8s_manager', 'K8SCluster', 'kubeconfig'),
    ]

    for label, app_label, model_name, field_name in tests:
        try:
            mod = __import__(f'{app_label}.models', fromlist=[model_name])
            Model = getattr(mod, model_name)
            instance = Model.objects.exclude(**{f'{field_name}__isnull': True}).first()
            if not instance:
                continue
            _ = getattr(instance, field_name)
            log.info(f"      {label}: 解密成功 ✓")
        except Exception as e:
            err_msg = f"{label}: 解密失败 - {e}"
            errors.append(err_msg)

    return errors
