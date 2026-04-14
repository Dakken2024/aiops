# -*- coding: utf-8 -*-
"""
Schema 迁移模块
从 SQLite 读取表结构，转换为 PostgreSQL DDL 并执行
包含: 类型映射、外键处理、索引创建、PgVector扩展安装
"""

import logging

log = logging.getLogger('Migrate.Schema')

TYPE_MAP = {
    'INTEGER': 'INTEGER',
    'INT': 'INTEGER',
    'BIGINT': 'BIGINT',
    'SMALLINT': 'SMALLINT',
    'TINYINT': 'SMALLINT',
    'REAL': 'DOUBLE PRECISION',
    'FLOAT': 'DOUBLE PRECISION',
    'DOUBLE': 'DOUBLE PRECISION',
    'NUMERIC': 'NUMERIC',
    'DECIMAL': 'NUMERIC',
    'TEXT': 'TEXT',
    'VARCHAR': 'TEXT',
    'CHAR': 'TEXT',
    'CLOB': 'TEXT',
    'BLOB': 'BYTEA',
    'BOOLEAN': 'BOOLEAN',
    'BOOL': 'BOOLEAN',
    'DATE': 'DATE',
    'DATETIME': 'TIMESTAMP WITH TIME ZONE',
    'TIMESTAMP': 'TIMESTAMP WITH TIME ZONE',
    'TIME': 'TIME',
    'JSON': 'JSONB',
}

SKIP_TABLES = {'sqlite_sequence', 'sqlite_master', 'django_migrations'}


def install_extensions(pg_conn):
    """安装 PostgreSQL 扩展 (PgVector, pg_trgm, btree_gin)"""
    extensions = [
        ('vector', 'PgVector 向量扩展'),
        ('pg_trgm', '三元组全文检索'),
        ('btree_gin', 'B-tree GIN 复合索引'),
    ]
    cur = pg_conn.cursor()
    for ext_name, desc in extensions:
        try:
            cur.execute(f"CREATE EXTENSION IF NOT EXISTS {ext_name}")
            log.info(f"  ✓ 扩展 {ext_name}: {desc}")
        except Exception as e:
            log.warning(f"  ⚠️ 扩展 {ext_name} 安装失败 (可忽略): {e}")
    cur.close()


def create_pg_schema(pg_conn, project_root):
    """
    方式1: 通过 Django ORM migrate 创建空表结构
    这是最安全的方式，确保与 Django 模型完全一致
    """
    import subprocess
    import sys
    import os

    env = os.environ.copy()
    env['PYTHONPATH'] = project_root

    cmd = [sys.executable, os.path.join(project_root, 'manage.py'), 'migrate',
           '--run-syncdb', '--noinput']

    result = subprocess.run(
        cmd, cwd=project_root,
        capture_output=True, text=True,
        timeout=120, env=env,
    )

    if result.returncode != 0:
        log.error(f"migrate 命令失败:\n{result.stderr[-1000:] if result.stderr else ''}")
        raise RuntimeError("Django migrate 创建 Schema 失败")

    log.info(f"  Django migrate 输出:\n{result.stdout[-500:]}")
    return True


def convert_sqlite_type_to_pg(sqlite_type):
    """SQLite 类型字符串 → PostgreSQL 类型"""
    st = str(sqlite_type).upper().strip()
    for pattern, pg_type in TYPE_MAP.items():
        if st.startswith(pattern) or pattern in st:
            return pg_type
    return 'TEXT'


def build_create_table_sql(table_name, columns, foreign_keys=None):
    """根据 SQLite PRAGMA 信息构建 PostgreSQL CREATE TABLE SQL"""
    col_defs = []
    pk_cols = []

    for col in columns:
        col_name = col['name']
        pg_type = convert_sqlite_type_to_pg(col['type'])

        if col['pk']:
            pk_cols.append(col_name)
            if col['type'].upper() in ('INTEGER', 'INT'):
                pg_type = 'BIGSERIAL'

        constraints = []
        if not col['pk'] and col.get('notnull'):
            constraints.append('NOT NULL')

        default_val = col.get('default')
        if default_val is not None and default_val != '':
            default_str = format_default_for_pg(default_val)
            if default_str:
                constraints.append(f'DEFAULT {default_str}')

        col_def = f'"{col_name}" {pg_type}'
        if constraints:
            col_def += ' ' + ' '.join(constraints)

        col_defs.append(col_def)

    if pk_cols:
        col_defs.append(f'PRIMARY KEY ({", ".join(pk_cols)})')

    sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" (\n  '
    sql += ',\n  '.join(col_defs)
    sql += '\n);'
    return sql


def format_default_for_pg(default_value):
    """转换 SQLite 默认值格式为 PostgreSQL 格式"""
    dv = str(default_value).strip()

    if dv.upper() == "NULL" or dv == '':
        return None

    if dv.upper() == "CURRENT_TIMESTAMP":
        return 'NOW()'

    if dv.startswith("'") or dv.startswith('"'):
        inner = dv[1:-1] if len(dv) >= 2 else dv
        return f"'{inner}'"

    try:
        int(dv)
        return dv
    except ValueError:
        pass

    try:
        float(dv)
        return dv
    except ValueError:
        pass

    return f"'{dv}'"


def create_indexes_from_sqlite(pg_conn, sqlite_conn, table_name):
    """将 SQLite 索引迁移到 PostgreSQL"""
    from .db_connections import get_sqlite_indexes
    indexes = get_sqlite_indexes(sqlite_conn, table_name)
    cur = pg_conn.cursor()

    for idx in indexes:
        idx_name = idx['name']
        if idx_name.startswith('sqlite_'):
            continue

        cols = idx['columns']
        unique = 'UNIQUE ' if idx['unique'] else ''

        safe_cols = ', '.join(f'"{c}"' for c in cols)
        sql = f'CREATE {unique}INDEX IF NOT EXISTS "{idx_name}" ON "{table_name}" ({safe_cols})'

        try:
            cur.execute(sql)
            log.debug(f"    索引 {idx_name}: OK")
        except Exception as e:
            log.warning(f"    索引 {idx_name} 跳过: {e}")

    cur.close()


def reset_sequences(pg_conn):
    """重置 PostgreSQL 自增序列值到最大 ID"""
    cur = pg_conn.cursor()
    cur.execute("""
        SELECT c.relname AS seq_name, a.attrelid::regclass AS table_name
        FROM pg_class c
        JOIN pg_depend d ON d.objid = c.oid
        JOIN pg_class a ON d.refobjid = a.oid
        JOIN pg_namespace n ON n.oid = a.relnamespace
        WHERE c.relkind = 'S' AND n.nspname = 'public'
    """)
    sequences = cur.fetchall()
    reset_count = 0

    for seq_name, table_name in sequences:
        table_str = str(table_name)
        if '"' in table_str:
            tname = table_str.split('"')[1]
        else:
            tname = table_str.replace('public.', '')

        try:
            cur.execute(f'SELECT setval(\'"{seq_name}"\', COALESCE((SELECT MAX(id) FROM "{tname}"), 1))')
            reset_count += 1
        except Exception as e:
            log.debug(f"    序列 {seq_name} 重置跳过: {e}")

    cur.close()
    log.info(f"  已重置 {reset_count} 个序列")
    return reset_count


def get_pgvector_setup_sql():
    """返回 PgVector 预留表的 DDL (用于未来 AI 功能)"""
    return """

-- =============================================
-- PgVector 预留: AI 运维知识库 (RAG)
-- =============================================

-- 为 AI 对话消息添加向量嵌入列 (1536维 OpenAI embedding)
DO $$ BEGIN
    ALTER TABLE ai_ops_chatmessage ADD COLUMN IF NOT EXISTS embedding VECTOR(1536);
EXCEPTION WHEN undefined_column OR undefined_table THEN NULL;
END $$;

-- AI 运维知识库表 (用于语义搜索)
CREATE TABLE IF NOT EXISTS ai_ops_knowledgebase (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    category VARCHAR(50) DEFAULT 'general',
    embedding VECTOR(1536),
    source_url VARCHAR(500),
    view_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE ai_ops_knowledgebase IS 'AI 运维知识库 (RAG)';
COMMENT ON COLUMN ai_ops_knowledgebase.embedding IS '文档向量嵌入，用于语义搜索';

-- 故障诊断案例库
CREATE TABLE IF NOT EXISTS aiops_incident_cases (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    symptoms TEXT,
    root_cause TEXT,
    solution TEXT,
    severity VARCHAR(20),
    symptoms_vec VECTOR(768),
    solution_vec VECTOR(768),
    tags TEXT[],
    created_by INTEGER REFERENCES system_user(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    is_verified BOOLEAN DEFAULT FALSE
);

COMMENT ON TABLE aiops_incident_cases IS '故障诊断案例库 (AI 学习素材)';

-- HNSW 索引 (高召回率向量索引)
CREATE INDEX IF NOT EXISTS idx_kb_embedding_hnsw
ON ai_ops_knowledgebase USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_incident_symptoms_hnsw
ON aiops_incident_cases USING hnsw (symptoms_vec vector_cosine_ops);
"""
