# -*- coding: utf-8 -*-
"""
数据库连接管理模块
统一管理 SQLite 和 PostgreSQL 连接，含连接池、重试、超时控制
"""

import sqlite3
import logging
import time

log = logging.getLogger('Migrate.DBConn')


def get_sqlite_connection(db_path, timeout=30):
    conn = sqlite3.connect(db_path, timeout=timeout)
    conn.row_factory = sqlite3.Row
    log.info(f"SQLite 连接成功: {db_path}")
    return conn


def get_pg_connection(config, autocommit=False):
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        raise ImportError("请先安装: pip install psycopg2-binary==2.9.9")

    host = config.get('host', 'localhost')
    port = config.get('port', 5432)
    user = config.get('user', 'postgres')
    password = config.get('password', '')
    dbname = config.get('dbname', 'aiops_db')

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            conn = psycopg2.connect(
                host=host, port=port,
                user=user, password=password,
                dbname=dbname,
                connect_timeout=10,
            )
            if autocommit:
                conn.autocommit = True
            else:
                conn.autocommit = False
            log.info(f"PostgreSQL 连接成功: {user}@{host}:{port}/{dbname}")
            return conn
        except Exception as e:
            log.warning(f"PostgreSQL 连接尝试 {attempt}/{max_retries} 失败: {e}")
            if attempt < max_retries:
                time.sleep(2 ** attempt)

    raise ConnectionError(f"无法连接到 PostgreSQL ({max_retries} 次尝试均失败)")


def test_pg_connection(config):
    """测试连接是否可用"""
    try:
        conn = get_pg_connection(config)
        cur = conn.cursor()
        cur.execute("SELECT version();")
        version = cur.fetchone()[0]
        cur.close()
        conn.close()
        return True, version
    except Exception as e:
        return False, str(e)


def get_sqlite_tables(conn):
    """获取 SQLite 所有表名"""
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    tables = [row[0] for row in cur.fetchall()]
    cur.close()
    return tables


def get_sqlite_table_info(conn, table_name):
    """获取表结构信息 (PRAGMA)"""
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info('{table_name}')")
    columns = []
    for row in cur.fetchall():
        columns.append({
            'cid': row[0],
            'name': row[1],
            'type': row[2],
            'notnull': bool(row[3]),
            'default': row[4],
            'pk': bool(row[5]),
        })
    cur.close()
    return columns


def get_sqlite_foreign_keys(conn, table_name):
    """获取外键信息"""
    cur = conn.cursor()
    cur.execute(f"PRAGMA foreign_key_list('{table_name}')")
    fks = []
    for row in cur.fetchall():
        fks.append({
            'id': row[0],
            'seq': row[1],
            'table': row[2],
            'from_col': row[3],
            'to_col': row[4],
        })
    cur.close()
    return fks


def get_sqlite_indexes(conn, table_name):
    """获取索引信息"""
    cur = conn.cursor()
    cur.execute(f"PRAGMA index_list('{table_name}')")
    indexes = []
    for row in cur.fetchall():
        idx_name = row[1]
        idx_unique = bool(row[2])
        cur2 = conn.cursor()
        cur2.execute(f"PRAGMA index_info('{idx_name}')")
        cols = [r[2] for r in cur2.fetchall()]
        cur2.close()
        indexes.append({'name': idx_name, 'unique': idx_unique, 'columns': cols})
    cur.close()
    return indexes


def get_table_row_count(conn, table_name):
    """获取表行数"""
    cur = conn.cursor()
    cur.execute(f'SELECT COUNT(*) FROM "{table_name}"')
    count = cur.fetchone()[0]
    cur.close()
    return count


def execute_in_batches(pg_conn, sql_template, data_iter, batch_size=500,
                       on_batch=None):
    """
    分批执行 INSERT 语句，避免内存溢出
    pg_conn: psycopg2 connection
    sql_template: INSERT INTO ... VALUES %s (使用 execute_values)
    data_iter: 可迭代的数据列表/生成器
    batch_size: 每批数量
    on_batch: 每批完成后的回调(batch_num, inserted_count)
    """
    from psycopg2.extras import execute_values
    total = 0
    batch_num = 0
    batch = []

    for row in data_iter:
        batch.append(row)
        if len(batch) >= batch_size:
            batch_num += 1
            with pg_conn.cursor() as cur:
                execute_values(cur, sql_template, batch)
            pg_conn.commit()
            total += len(batch)
            if on_batch:
                on_batch(batch_num, len(batch))
            batch = []

    if batch:
        batch_num += 1
        with pg_conn.cursor() as cur:
            execute_values(cur, sql_template, batch)
        pg_conn.commit()
        total += len(batch)
        if on_batch:
            on_batch(batch_num, len(batch))

    return total
