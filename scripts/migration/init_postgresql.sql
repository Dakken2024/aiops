-- ============================================================
-- AiOps PostgreSQL 18 初始化脚本
-- 用途: 创建数据库、安装扩展、设置权限
-- 执行: psql -U postgres -f init_postgresql.sql
-- ============================================================

\echo '============================================'
\echo '  AiOps PostgreSQL 18 初始化'
\echo '============================================'

-- 1. 创建数据库 (如不存在)
SELECT 'CREATE DATABASE aiops_db WITH ENCODING = '\''UTF8'\'' TEMPLATE = template0'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'aiops_db')\gexec

\c aiops_db;

-- 2. 安装扩展
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gin;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

\echo '✓ Extensions installed: vector, pg_trgm, btree_gin, pg_stat_statements'

-- 3. 创建 PgVector 预留表 (AI 知识库)
DROP TABLE IF EXISTS ai_ops_knowledgebase CASCADE;
DROP TABLE IF EXISTS aiops_incident_cases CASCADE;

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

CREATE INDEX idx_kb_embedding_hnsw
ON ai_ops_knowledgebase USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

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
    created_by INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    is_verified BOOLEAN DEFAULT FALSE
);

COMMENT ON TABLE aiops_incident_cases IS '故障诊断案例库 (AI 学习素材)';

CREATE INDEX idx_incident_symptoms_hnsw
ON aiops_incident_cases USING hnsw (symptoms_vec vector_cosine_ops);

\echo '✓ AI tables created: knowledgebase, incident_cases'

-- 4. 性能优化配置
ALTER DATABASE aiops_db SET statement_timeout = '30s';
ALTER DATABASE aiops_db SET lock_timeout = '5s';
ALTER DATABASE aiops_db SET idle_in_transaction_session_timeout = '10min';
ALTER DATABASE aiops_db SET work_mem = '64MB';
ALTER DATABASE aiops_db SET maintenance_work_mem = '256MB';
ALTER DATABASE aiops_db SET random_page_cost = 1.1;
ALTER DATABASE aiops_db SET effective_cache_size = '4GB';

\echo '✓ Performance tuning applied'

-- 5. 显示版本信息
SELECT version();
SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector', 'pg_trgm', 'btree_gin');

\echo ''
\echo '============================================'
\echo '  ✅ PostgreSQL 初始化完成!'
\echo '============================================'
\echo '下一步: 运行 python scripts/migration/run_migration.py'
