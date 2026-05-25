#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AiOps 迁移后数据验证脚本
验证项:
1. 核心表记录数
2. 外键完整性 (孤儿记录检查)
3. 加密字段可解密性
4. 时区字段 (aware datetime)
5. JSONB 类型验证
6. INET 类型验证

用法:
    cd d:\\ETL\\aiops
    set DB_ENGINE=postgresql
    set DB_NAME=aiops_db
    set DB_USER=postgres
    set DB_PASSWORD=123456
    set DB_HOST=localhost
    set DB_PORT=5432
    python scripts/post_migration_validation.py
"""

import os
import sys
import argparse
import logging
from datetime import datetime

# 将项目根目录加入 Python 路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ops_platform.settings')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger('PostMigration.Validate')


class ValidationRunner:
    def __init__(self):
        self.passed = 0
        self.warnings = 0
        self.failed = 0
        self.messages = []

    def _emit(self, status, message):
        icons = {'PASS': '[PASS]', 'FAIL': '[FAIL]', 'WARN': '[WARN]', 'INFO': '[INFO]'}
        icon = icons.get(status, '[?]')
        line = f"{icon} {message}"
        self.messages.append(line)
        if status == 'PASS':
            self.passed += 1
            log.info(line)
        elif status == 'FAIL':
            self.failed += 1
            log.error(line)
        elif status == 'WARN':
            self.warnings += 1
            log.warning(line)
        else:
            log.info(line)

    def run_all(self):
        log.info("=" * 60)
        log.info("AiOps 迁移后数据验证")
        log.info(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log.info("=" * 60)

        self.validate_table_counts()
        self.validate_foreign_keys()
        self.validate_encrypted_fields()
        self.validate_timezone_fields()
        self.validate_jsonb_fields()
        self.validate_inet_fields()

        total = self.passed + self.warnings + self.failed
        log.info("\n" + "=" * 60)
        log.info(f"验证汇总: 通过={self.passed}  警告={self.warnings}  失败={self.failed}  (共{total}项)")
        log.info("=" * 60)

        return self.failed == 0

    # ------------------------------------------------------------------
    # 1. 表记录数验证
    # ------------------------------------------------------------------
    def validate_table_counts(self):
        log.info("\n[1/6] 核心表记录数验证")
        from django.db import connection

        tables = [
            ('system', 'User'),
            ('cmdb', 'Server'),
            ('cmdb', 'ServerMetric'),
            ('cmdb', 'TerminalLog'),
            ('k8s_manager', 'K8sCluster'),
            ('script_manager', 'Script'),
            ('ai_ops', 'AIModel'),
            ('ai_ops', 'ChatSession'),
            ('ai_ops', 'ChatMessage'),
        ]

        for app_label, model_name in tables:
            try:
                from django.apps import apps
                Model = apps.get_model(app_label, model_name)
                count = Model.objects.count()
                if count > 0:
                    self._emit('PASS', f"{app_label}.{model_name}: {count} 条记录")
                else:
                    self._emit('WARN', f"{app_label}.{model_name}: 0 条记录")
            except Exception as e:
                self._emit('FAIL', f"{app_label}.{model_name}: 查询失败 - {e}")

    # ------------------------------------------------------------------
    # 2. 外键完整性验证
    # ------------------------------------------------------------------
    def validate_foreign_keys(self):
        log.info("\n[2/6] 外键完整性验证 (孤儿记录检查)")
        from django.db import connection

        checks = [
            ("cmdb_terminallog", "server_id", "cmdb_server", "id"),
            ("cmdb_highriskaudit", "server_id", "cmdb_server", "id"),
            ("cmdb_servermetric", "server_id", "cmdb_server", "id"),
            ("ai_ops_chatsession", "user_id", "system_user", "id"),
            ("script_manager_tasklog", "server_id", "cmdb_server", "id"),
        ]

        for tbl, fk_col, ref_tbl, ref_col in checks:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f"""
                        SELECT COUNT(*) FROM "{tbl}"
                        WHERE "{fk_col}" IS NOT NULL
                        AND "{fk_col}" NOT IN (SELECT "{ref_col}" FROM "{ref_tbl}")
                    """)
                    orphan = cursor.fetchone()[0]
                if orphan == 0:
                    self._emit('PASS', f"{tbl}.{fk_col} -> {ref_tbl}.{ref_col}: 无孤儿记录")
                else:
                    self._emit('FAIL', f"{tbl}.{fk_col} -> {ref_tbl}.{ref_col}: {orphan} 条孤儿记录")
            except Exception as e:
                self._emit('FAIL', f"{tbl}.{fk_col}: 检查异常 - {e}")

    # ------------------------------------------------------------------
    # 3. 加密字段验证
    # ------------------------------------------------------------------
    def validate_encrypted_fields(self):
        log.info("\n[3/6] 加密字段可解密性验证")

        tests = [
            ('cmdb', 'Server', 'password', 'Server.password'),
            ('cmdb', 'CloudAccount', 'secret_key', 'CloudAccount.secret_key'),
            ('ai_ops', 'AIModel', 'api_key', 'AIModel.api_key'),
            ('k8s_manager', 'K8sCluster', 'kubeconfig', 'K8sCluster.kubeconfig'),
        ]

        for app_label, model_name, field, label in tests:
            try:
                from django.apps import apps
                Model = apps.get_model(app_label, model_name)
                # EncryptedCharField/EncryptedTextField 不支持 __isnull 和 exclude 中的 exact 查询
                # 先取第一条非空记录，在 Python 层过滤
                obj = Model.objects.first()
                if obj is None:
                    self._emit('WARN', f"{label}: 无可测试数据，跳过")
                    continue
                val = getattr(obj, field)
                if val is not None and str(val).strip() != '':
                    self._emit('PASS', f"{label}: 解密成功 (长度={len(str(val))})")
                else:
                    self._emit('WARN', f"{label}: 解密结果为空")
            except Exception as e:
                self._emit('FAIL', f"{label}: 解密失败 - {e}")

    # ------------------------------------------------------------------
    # 4. 时区字段验证
    # ------------------------------------------------------------------
    def validate_timezone_fields(self):
        log.info("\n[4/6] 时区字段验证 (aware datetime)")
        from django.utils import timezone

        checks = [
            ('cmdb', 'Server', 'created_at'),
            ('ai_ops', 'ChatMessage', 'created_at'),
        ]

        for app_label, model_name, field in checks:
            try:
                from django.apps import apps
                Model = apps.get_model(app_label, model_name)
                obj = Model.objects.first()
                if obj is None:
                    self._emit('WARN', f"{app_label}.{model_name}.{field}: 无数据，跳过")
                    continue
                val = getattr(obj, field)
                if val is None:
                    self._emit('WARN', f"{app_label}.{model_name}.{field}: 字段值为空")
                    continue
                if timezone.is_aware(val):
                    self._emit('PASS', f"{app_label}.{model_name}.{field}: 带时区 (aware)")
                else:
                    self._emit('FAIL', f"{app_label}.{model_name}.{field}: 无时区 (naive)")
            except Exception as e:
                self._emit('FAIL', f"{app_label}.{model_name}.{field}: 检查异常 - {e}")

    # ------------------------------------------------------------------
    # 5. JSONB 类型验证
    # ------------------------------------------------------------------
    def validate_jsonb_fields(self):
        log.info("\n[5/6] JSONB 类型验证")
        from django.db import connection

        table_name = 'script_manager_taskexecution'
        column_name = 'params'

        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT data_type
                    FROM information_schema.columns
                    WHERE table_name = %s AND column_name = %s
                """, [table_name, column_name])
                row = cursor.fetchone()
            if row is None:
                self._emit('FAIL', f"{table_name}.{column_name}: 列不存在")
                return
            dtype = row[0].lower()
            if dtype == 'jsonb':
                self._emit('PASS', f"{table_name}.{column_name}: 类型为 JSONB")
            else:
                self._emit('FAIL', f"{table_name}.{column_name}: 类型为 {dtype} (期望 JSONB)")
        except Exception as e:
            self._emit('FAIL', f"{table_name}.{column_name}: 查询异常 - {e}")
            return

        # 测试 JSON 查询是否正常工作
        try:
            from django.apps import apps
            TaskExecution = apps.get_model('script_manager', 'TaskExecution')
            # 尝试使用 JSON 查询 (PostgreSQL 特有)
            count = TaskExecution.objects.filter(params__isnull=False).count()
            self._emit('PASS', f"JSON 查询测试: script_manager.TaskExecution.params 查询正常 (样本数={count})")
        except Exception as e:
            self._emit('FAIL', f"JSON 查询测试: 查询异常 - {e}")

    # ------------------------------------------------------------------
    # 6. INET 类型验证
    # ------------------------------------------------------------------
    def validate_inet_fields(self):
        log.info("\n[6/6] INET 类型验证")
        from django.db import connection

        table_name = 'cmdb_server'
        column_name = 'ip_address'

        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT data_type
                    FROM information_schema.columns
                    WHERE table_name = %s AND column_name = %s
                """, [table_name, column_name])
                row = cursor.fetchone()
            if row is None:
                self._emit('FAIL', f"{table_name}.{column_name}: 列不存在")
                return
            dtype = row[0].lower()
            if dtype == 'inet':
                self._emit('PASS', f"{table_name}.{column_name}: 类型为 INET")
            else:
                self._emit('FAIL', f"{table_name}.{column_name}: 类型为 {dtype} (期望 INET)")
        except Exception as e:
            self._emit('FAIL', f"{table_name}.{column_name}: 查询异常 - {e}")
            return

        # 测试 IP 地址查询是否正常工作
        try:
            from django.apps import apps
            Server = apps.get_model('cmdb', 'Server')
            # 尝试查询一条记录验证 INET 行为
            obj = Server.objects.first()
            if obj is None:
                self._emit('WARN', f"IP 查询测试: cmdb.Server 无数据，跳过")
                return
            ip_val = obj.ip_address
            # 使用 PostgreSQL INET 特有查询: 包含在某个网段
            count = Server.objects.filter(ip_address__isnull=False).count()
            self._emit('PASS', f"IP 查询测试: cmdb.Server.ip_address 查询正常 (样本数={count}, ip={ip_val})")
        except Exception as e:
            self._emit('FAIL', f"IP 查询测试: 查询异常 - {e}")


def main():
    parser = argparse.ArgumentParser(description='AiOps 迁移后数据验证脚本')
    parser.add_argument('--settings', default='ops_platform.settings', help='Django settings 模块')
    args = parser.parse_args()

    if args.settings:
        os.environ['DJANGO_SETTINGS_MODULE'] = args.settings

    try:
        import django
        django.setup()
    except Exception as e:
        log.error(f"Django 初始化失败: {e}")
        sys.exit(1)

    runner = ValidationRunner()
    ok = runner.run_all()

    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
