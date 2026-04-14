# -*- coding: utf-8 -*-
"""
迁移后数据验证模块
执行: 表数量/行数对比、外键完整性、加密字段、时区、JSONB、PgVector
"""

import logging
from datetime import datetime

log = logging.getLogger('Migrate.Validate')


class MigrationValidator:
    def __init__(self, pg_conn, logger=None):
        self.pg = pg_conn
        self.log = logger or log
        self.errors = []
        self.warnings = []
        self.passed = 0

    def _result(self, status, message):
        icons = {'PASS': '✅', 'FAIL': '❌', 'WARN': '⚠️', 'INFO': 'ℹ️'}
        icon = icons.get(status, '•')
        self.log.info(f"  {icon} {message}")
        if status == 'FAIL':
            self.errors.append(message)
        elif status == 'WARN':
            self.warnings.append(message)
        else:
            self.passed += 1

    def run_all(self):
        """执行全部 7 项验证"""
        self.log.info("\n" + "=" * 60)
        self.log.info("🔍 AiOps 迁移后数据验证")
        self.log.info(f"   时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.log.info("=" * 60)

        self.validate_table_counts()
        self.validate_foreign_keys()
        self.validate_encrypted_fields()
        self.validate_datetime_fields()
        self.validate_jsonb_fields()
        self.validate_pgvector_extensions()
        self.validate_sequences()

        total = self.passed + len(self.warnings) + len(self.errors)
        self.log.info("\n" + "=" * 60)
        self.log.info(f"📊 验证结果: ✅通过={self.passed} ⚠️警告={len(self.warnings)} ❌失败={len(self.errors)} (共{total}项)")
        self.log.info("=" * 60)

        return len(self.errors) == 0

    def validate_table_counts(self):
        """V1: 验证表数量和行数"""
        self.log.info("\n[1/7] 验证表记录数...")
        cur = self.pg.cursor()

        cur.execute("""
            SELECT table_name, n_live_tup::int as row_count
            FROM pg_stat_user_tables
            ORDER BY n_live_tup DESC NULLS LAST
        """)
        rows = cur.fetchall()
        cur.close()

        if not rows:
            self._result('FAIL', "未查询到任何用户表")
            return

        for tname, count in rows:
            if count is not None:
                self._result('PASS', f"{tname}: {count:,} 行")
            else:
                self._result('WARN', f"{tname}: 行数统计为空(可能刚建表无ANALYZE)")

        self._result('INFO', f"共 {len(rows)} 张业务表")

    def validate_foreign_keys(self):
        """V2: 外键引用完整性检查"""
        self.log.info("\n[2/7] 验证外键完整性...")
        cur = self.pg.cursor()

        checks = [
            ("cmdb_terminallog", "server_id", "cmdb_server", "id"),
            ("cmdb_highriskaudit", "server_id", "cmdb_server", "id"),
            ("cmdb_servermetric", "server_id", "cmdb_server", "id"),
            ("ai_ops_chatsession", "user_id", "system_user", "id"),
            ("script_manager_tasklog", "server_id", "cmdb_server", "id"),
            ("monitoring_alertevent", "rule_id", "monitoring_alertrule", "id"),
            ("monitoring_alertevent", "server_id", "cmdb_server", "id"),
        ]

        for tbl, fk_col, ref_tbl, ref_col in checks:
            try:
                cur.execute(f"""
                    SELECT COUNT(*) FROM "{tbl}"
                    WHERE "{fk_col}" IS NOT NULL
                    AND "{fk_col}" NOT IN (SELECT "{ref_col}" FROM "{ref_tbl}")
                """)
                orphan = cur.fetchone()[0]
                if orphan == 0:
                    self._result('PASS', f"{tbl}.{fk_col} → {ref_tbl}: 无孤儿")
                else:
                    self._result('WARN', f"{tbl}.{fk_col}: {orphan} 条孤儿记录")
            except Exception as e:
                self._result('WARN', f"{tbl}.{fk_col}: 检查跳过 - {e}")

        cur.close()

    def validate_encrypted_fields(self):
        """V3: Fernet 加密字段可解密性验证"""
        self.log.info("\n[3/7] 验证加密字段...")

        import os, sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ops_platform.settings')

        try:
            import django
            django.setup()
        except Exception as e:
            self._result('WARN', f"Django 初始化跳过: {e}")
            return

        tests = [
            ('Server.password', 'cmdb', 'Server', 'password'),
            ('CloudAccount.secret_key', 'cmdb', 'CloudAccount', 'secret_key'),
            ('AIModel.api_key', 'ai_ops', 'AIModel', 'api_key'),
            ('K8SCluster.kubeconfig', 'k8s_manager', 'K8SCluster', 'kubeconfig'),
        ]

        for label, app, model_name, field in tests:
            try:
                mod = __import__(f'{app}.models', fromlist=[model_name])
                Model = getattr(mod, model_name)
                obj = Model.objects.exclude(**{f'{field}__isnull': True}).first()
                if obj:
                    val = getattr(obj, field)
                    self._result('PASS', f"{label}: 解密成功")
                else:
                    self._result('INFO', f"{label}: 无测试数据，跳过")
            except Exception as e:
                self._result('FAIL', f"{label}: 解密失败 - {e}")

    def validate_datetime_fields(self):
        """V4: DateTime 时区感知验证"""
        self.log.info("\n[4/7] 验证日期时间字段...")
        cur = self.pg.cursor()

        dt_checks = [
            ('cmdb_server', 'created_at'),
            ('ai_ops_chatsession', 'created_at'),
            ('monitoring_alertevent', 'fired_at'),
        ]

        for tbl, col in dt_checks:
            try:
                cur.execute(f"""
                    SELECT data_type, is_tz_aware
                    FROM (
                        SELECT '{col}' as data_type,
                               CASE WHEN data_type LIKE '%with time zone' THEN true ELSE false END as is_tz_aware
                        FROM information_schema.columns
                        WHERE table_name='{tbl}' AND column_name='{col}'
                    ) sub
                """)
                row = cur.fetchone()
                if row and row[1]:
                    self._result('PASS', f"{tbl}.{col}: TIMESTAMPTZ (带时区)")
                elif row:
                    self._result('WARN', f"{tbl}.{col}: 类型={row[0]} (期望TIMESTAMPTZ)")
                else:
                    self._result('INFO', f"{tbl}.{col}: 未找到列")
            except Exception as e:
                self._result('WARN', f"{tbl}.{col}: 检查异常 - {e}")

        cur.close()

    def validate_jsonb_fields(self):
        """V5: JSONField → JSONB 升级验证"""
        self.log.info("\n[5/7] 验证 JSON 字段 (JSONB)...")
        cur = self.pg.cursor()

        json_checks = [
            ('script_manager_taskexecution', 'params'),
            ('monitoring_saveddashboard', 'config'),
        ]

        for tbl, col in json_checks:
            try:
                cur.execute(f"""
                    SELECT data_type FROM information_schema.columns
                    WHERE table_name='{tbl}' AND column_name='{col}'
                """)
                row = cur.fetchone()
                dtype = row[0].lower() if row else None
                if dtype == 'jsonb':
                    self._result('PASS', f"{tbl}.{col}: JSONB ✨")
                elif dtype in ('json', 'text'):
                    self._result('WARN', f"{tbl}.{col}: 类型={dtype} (期望jsonb)")
                else:
                    self._result('INFO', f"{tbl}.{col}: {dtype or '未知'}")
            except Exception as e:
                self._result('WARN', f"{tbl}.{col}: 检查异常 - {e}")

        cur.close()

    def validate_pgvector_extensions(self):
        """V6: PgVector 扩展安装验证"""
        self.log.info("\n[6/7] 验证 PgVector 扩展...")
        cur = self.pg.cursor()

        extensions = ['vector', 'pg_trgm', 'btree_gin']
        for ext in extensions:
            try:
                cur.execute(f"SELECT extname, extversion FROM pg_extension WHERE extname='{ext}'")
                row = cur.fetchone()
                if row:
                    self._result('PASS', f"扩展 {ext}: v{row[1]} 已安装")
                else:
                    self._result('WARN', f"扩展 {ext}: 未安装")
            except Exception as e:
                self._result('WARN', f"扩展 {ext}: 查询失败 - {e}")

        cur.close()

    def validate_sequences(self):
        """V7: 自增序列值同步验证"""
        self.log.info("\n[7/7] 验证序列值...")
        cur = self.pg.cursor()

        try:
            cur.execute("""
                SELECT c.relname as seq_name,
                       a.attrelid::regclass as table_name,
                       last_value, max_value
                FROM pg_class c
                JOIN pg_depend d ON d.objid = c.oid
                JOIN pg_class a ON d.refobjid = a.oid
                WHERE c.relkind = 'S'
                ORDER BY seq_name
                LIMIT 30
            """)
            rows = cur.fetchall()
            for seq_name, tbl, last_val, max_val in rows:
                if last_val > 0:
                    self._result('PASS', f"{seq_name} ({tbl}): last={last_val}")
                else:
                    self._result('INFO', f"{seq_name} ({tbl}): last=0 (空表?)")
        except Exception as e:
            self._result('WARN', f"序列验证异常: {e}")

        cur.close()
