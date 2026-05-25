-- ============================================================
-- AiOps PostgreSQL 18 初始化脚本
-- 在容器首次启动时自动执行（通过 docker-entrypoint-initdb.d）
-- ============================================================

-- 1. 启用 pgvector 向量扩展（用于 AI 嵌入和相似性搜索）
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. 启用 pg_trgm 扩展（用于模糊文本搜索和相似度匹配）
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 3. 启用 btree_gin 扩展（用于 GIN 索引与 B-tree 的复合优化）
CREATE EXTENSION IF NOT EXISTS btree_gin;

-- 4. 创建 aiops_user 用户（如果不存在）并授权
DO
$$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'aiops_user'
    ) THEN
        CREATE USER aiops_user WITH PASSWORD 'aiops_user';
    END IF;
END
$$;

-- 授予 aiops_user 对 aiops_db 数据库的所有权限
GRANT ALL PRIVILEGES ON DATABASE aiops_db TO aiops_user;

-- 授予对 public schema 的权限
GRANT ALL ON SCHEMA public TO aiops_user;
