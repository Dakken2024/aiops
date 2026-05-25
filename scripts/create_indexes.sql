-- ============================================================
-- PostgreSQL 性能优化索引脚本
-- 使用 CREATE INDEX CONCURRENTLY 避免锁表，适合生产环境执行
-- 执行前请确保数据库连接正常，且没有长时间运行的事务
-- ============================================================

-- 确保 pg_trgm 扩展已启用（用于 GIN 全文搜索索引）
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ------------------------------------------------------------
-- 1. ServerMetric 复合索引: (server_id, created_at DESC)
-- 用途: 加速按服务器查询最近性能指标，如仪表盘趋势图、实时监控面板
-- 场景: WHERE server_id = ? ORDER BY created_at DESC LIMIT N
-- ------------------------------------------------------------
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_servermetric_server_created
    ON cmdb_servermetric (server_id, created_at DESC);

COMMENT ON INDEX idx_servermetric_server_created IS
    'ServerMetric 复合索引：加速按服务器查询最近性能指标（仪表盘趋势图、实时监控）';

-- ------------------------------------------------------------
-- 2. ServerMetric 最近数据部分索引: (created_at DESC) WHERE created_at > NOW() - INTERVAL '7 days'
-- 用途: 仅索引最近7天的数据，大幅减少索引体积，加速近期数据查询
-- 场景: 仪表盘默认只展示最近7天数据，此索引避免扫描全表历史数据
-- ------------------------------------------------------------
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_servermetric_recent_7d
    ON cmdb_servermetric (created_at DESC)
    WHERE created_at > NOW() - INTERVAL '7 days';

COMMENT ON INDEX idx_servermetric_recent_7d IS
    'ServerMetric 最近7天部分索引：仅索引热数据，加速仪表盘默认7天视图查询，减少索引体积';

-- ------------------------------------------------------------
-- 3. TerminalLog 用户+时间索引: (user_id, start_time DESC)
-- 用途: 加速查询某个用户的 WebSSH 操作审计记录，按时间倒序展示
-- 场景: 审计页面按用户筛选操作记录，用户个人中心查看自己的操作历史
-- ------------------------------------------------------------
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_terminallog_user_starttime
    ON cmdb_terminallog (user_id, start_time DESC);

COMMENT ON INDEX idx_terminallog_user_starttime IS
    'TerminalLog 用户+时间索引：加速按用户查询 WebSSH 审计记录，支持审计追溯和个人操作历史';

-- ------------------------------------------------------------
-- 4. HighRiskAudit 全文搜索 GIN 索引: USING gin (command gin_trgm_ops)
-- 用途: 加速高危命令的内容模糊搜索/全文检索
-- 场景: 安全审计中按命令关键词（如 "rm -rf", "drop table"）快速检索相关记录
-- 依赖: 需要提前安装 pg_trgm 扩展（脚本开头已处理）
-- ------------------------------------------------------------
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_highriskaudit_command_gin
    ON cmdb_highriskaudit USING gin (command gin_trgm_ops);

COMMENT ON INDEX idx_highriskaudit_command_gin IS
    'HighRiskAudit 全文搜索 GIN 索引：基于 trigram 加速高危命令的模糊搜索，支持安全审计关键词检索';

-- ------------------------------------------------------------
-- 5. ChatMessage 会话索引: (session_id, created_at ASC)
-- 用途: 加速按会话加载聊天消息列表，按时间正序展示对话上下文
-- 场景: AI 对话页面打开某个会话时，快速加载该会话的全部历史消息
-- ------------------------------------------------------------
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chatmessage_session_created
    ON ai_ops_chatmessage (session_id, created_at ASC);

COMMENT ON INDEX idx_chatmessage_session_created IS
    'ChatMessage 会话索引：加速按会话加载历史消息，支持 AI 对话上下文快速渲染';

-- ------------------------------------------------------------
-- 6. TaskLog 执行状态索引: (status, execution_id)
-- 用途: 加速按执行批次和状态筛选任务日志，如查看某次批量任务中失败的节点
-- 场景: 任务详情页按状态（Pending/Running/Success/Failed）过滤日志列表
-- ------------------------------------------------------------
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tasklog_status_execution
    ON script_manager_tasklog (status, execution_id);

COMMENT ON INDEX idx_tasklog_status_execution IS
    'TaskLog 执行状态索引：加速按执行批次和状态筛选任务日志，优化批量任务详情页查询';

-- ------------------------------------------------------------
-- 7. ConfigMapHistory 版本索引: (cluster_id, namespace, name, version DESC)
-- 用途: 加速查询某个 ConfigMap 的历史版本列表，支持快速回滚到指定版本
-- 场景: K8s 配置管理页面查看某个 ConfigMap 的变更历史，按版本号倒序展示
-- ------------------------------------------------------------
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_configmaphistory_version
    ON k8s_manager_configmaphistory (cluster_id, namespace, name, version DESC);

COMMENT ON INDEX idx_configmaphistory_version IS
    'ConfigMapHistory 版本索引：加速查询指定 ConfigMap 的历史版本，支持 K8s 配置回滚和变更追溯';

-- ============================================================
-- 索引创建完成。可通过以下语句查看新索引的统计信息：
-- SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' AND indexname LIKE 'idx_%';
-- ============================================================
