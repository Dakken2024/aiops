# -*- coding: utf-8 -*-
"""
数据迁移核心模块
负责: 逐表读取SQLite数据、类型转换、批量写入PostgreSQL
支持: 大数据量分批处理、进度报告、错误跳过
"""

import logging
import time
from datetime import datetime

log = logging.getLogger('Migrate.Data')

SKIP_TABLES = {'sqlite_sequence', 'sqlite_master', 'django_migrations'}

BINARY_FIELDS = {
    'cmdb_server.password', 'cmdb_server.ssh_key',
    'cmdb_cloudaccount.secret_key',
    'ai_ops_aimodel.api_key',
    'k8s_manager_k8scluster.kubeconfig',
}

DATETIME_FIELDS = set()
JSON_FIELDS = {
    'script_manager_taskexecution.params',
    'monitoring_alertrule.match_conditions',
    'monitoring_alertrule.match_rules',
    'monitoring_escalationpolicy.escalation_steps',
    'monitoring_escalationpolicy.match_rules',
    'monitoring_saveddashboard.config',
}


class DataMigrator:
    def __init__(self, sqlite_conn, pg_conn, logger=None):
        self.sqlite = sqlite_conn
        self.pg = pg_conn
        self.log = logger or log
        self.stats = {'tables': 0, 'rows': 0, 'errors': 0, 'skipped': 0}

    def migrate_all(self):
        """迁移所有表数据"""
        from .db_connections import (get_sqlite_tables, get_sqlite_table_info,
                                     get_table_row_count)
        tables = get_sqlite_tables(self.sqlite)

        self.log.info(f"  发现 {len(tables)} 张表")

        for table_name in tables:
            if table_name in SKIP_TABLES:
                self.log.debug(f"    跳过系统表: {table_name}")
                continue

            try:
                self.migrate_table(table_name)
            except Exception as e:
                self.log.error(f"    ❌ 表 {table_name} 迁移失败: {e}")
                self.stats['errors'] += 1

        return self.stats

    def migrate_table(self, table_name):
        """迁移单张表"""
        from .db_connections import get_sqlite_table_info, get_table_row_count

        columns = get_sqlite_table_info(self.sqlite, table_name)
        if not columns:
            self.log.warning(f"    表 {table_name} 无列信息，跳过")
            return

        col_names = [c['name'] for c in columns]
        row_count = get_table_row_count(self.sqlite, table_name)

        if row_count == 0:
            self.log.info(f"    ✓ {table_name}: 空表，跳过")
            return

        self.log.info(f"    → {table_name}: {row_count} 行, {len(col_names)} 列...")

        t0 = time.time()
        inserted = self._transfer_data(table_name, col_names, row_count)
        elapsed = time.time() - t0

        self.stats['tables'] += 1
        self.stats['rows'] += inserted
        rate = row_count / elapsed if elapsed > 0 else 0
        self.log.info(f"    ✓ {table_name}: {inserted}/{row_count} 行 ({elapsed:.1f}s, {rate:.0f}行/s)")

    def _transfer_data(self, table_name, col_names, total_rows):
        """核心数据传输逻辑"""
        from psycopg2.extras import execute_values

        cur_s = self.sqlite.cursor()
        cur_p = self.pg.cursor()

        cols_str = ', '.join(f'"{c}"' for c in col_names)
        select_sql = f'SELECT {cols_str} FROM "{table_name}"'
        insert_template = f'INSERT INTO "{table_name}" ({cols_str}) VALUES %s ON CONFLICT DO NOTHING'

        full_key = None
        batch = []
        batch_size = 1000
        inserted_total = 0
        batch_num = 0

        cur_s.execute(select_sql)
        while True:
            rows = cur_s.fetchmany(batch_size)
            if not rows:
                break

            converted_batch = []
            for row in rows:
                converted = self._convert_row(row, col_names, table_name)
                if converted is not None:
                    converted_batch.append(tuple(converted))

            if converted_batch:
                try:
                    execute_values(cur_p, insert_template, converted_batch)
                    self.pg.commit()
                    inserted_total += len(converted_batch)
                except Exception as e:
                    self.pg.rollback()
                    self.log.warning(f"      批次写入失败(尝试单行): {e}")
                    single_inserted = 0
                    for conv_row in converted_batch:
                        try:
                            s_cur = self.pg.cursor()
                            s_cur.execute(
                                f'INSERT INTO "{table_name}" ({cols_str}) VALUES ({",".join(["%s"]*len(col_names))}) '
                                f'ON CONFLICT DO NOTHING',
                                list(conv_row)
                            )
                            self.pg.commit()
                            single_inserted += 1
                        except Exception:
                            self.pg.rollback()
                    inserted_total += single_inserted

            batch_num += 1
            if batch_num % 10 == 0 or not rows:
                self.log.debug(f"      进度: {inserted_total}/{total_rows}")

        cur_s.close()
        cur_p.close()
        return inserted_total

    def _convert_row(self, row, col_names, table_name):
        """
        将一行 SQLite 数据转换为 PostgreSQL 兼容格式
        处理: NULL值、日期时间、二进制、布尔、JSON等特殊类型
        """
        result = []
        for i, col_name in enumerate(col_names):
            val = row[i] if i < len(row) else None
            full_key = f"{table_name}.{col_name}"

            if val is None:
                result.append(None)
                continue

            if isinstance(val, bytes):
                result.append(val)
                continue

            if isinstance(val, str):
                if full_key in JSON_FIELDS:
                    import json
                    try:
                        result.append(json.loads(val) if val else None)
                    except (json.JSONDecodeError, TypeError):
                        result.append(val)
                elif full_key in BINARY_FIELDS:
                    try:
                        result.append(bytes(val, 'utf-8'))
                    except Exception:
                        result.append(val.encode('utf-8'))
                else:
                    result.append(val)
                continue

            if isinstance(val, bool):
                result.append(val)
                continue

            if isinstance(val, (int, float)):
                result.append(val)
                continue

            result.append(str(val))

        return result


class FastDataMigrator(DataMigrator):
    """使用 COPY 协议的高速迁移器 (适用于大数据量表)"""

    def _transfer_data(self, table_name, col_names, total_rows):
        """使用 psycopg2 copy_expert 高速导入"""
        import io
        import csv

        cols_str = ', '.join(f'"{c}"' for c in col_names)
        select_sql = f'SELECT {cols_str} FROM "{table_name}"'

        cur_s = self.sqlite.cursor()
        cur_s.execute(select_sql)

        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter='\t', quoting=csv.QUOTE_MINIMAL,
                             doublequote=False, escapechar='\\')
        written = 0

        for row in cur_s.fetchall():
            converted = self._convert_row(row, col_names, table_name)
            if converted:
                writer.writerow([self._format_copy_val(v) for v in converted])
                written += 1

        cur_s.close()

        if written == 0:
            return 0

        buffer.seek(0)
        cur_p = self.pg.cursor()

        try:
            sql = f'COPY "{table_name}" ({cols_str}) FROM STDIN WITH (FORMAT text)'
            cur_p.copy_expert(sql, buffer)
            self.pg.commit()
        except Exception as e:
            self.pg.rollback()
            self.log.warning(f"      COPY 模式失败，回退到普通模式: {e}")
            return super()._transfer_data(table_name, col_names, total_rows)
        finally:
            cur_p.close()

        return written

    @staticmethod
    def _format_copy_val(val):
        """格式化值为 COPY 协议兼容格式"""
        if val is None:
            return '\\N'
        if isinstance(val, bool):
            return 't' if val else 'f'
        if isinstance(val, (list, dict)):
            import json
            return json.dumps(val, ensure_ascii=False)
        if isinstance(val, datetime):
            return val.isoformat()
        return str(val)
