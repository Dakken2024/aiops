# SQLite to PostgreSQL 18 数据库迁移 Spec

## Why
AiOps 平台当前使用 SQLite 作为开发/生产数据库，随着监控指标数据量增长和并发写入需求增加，SQLite 的写锁机制已成为性能瓶颈。迁移至 PostgreSQL 18 可提升并发性能 100x+，并为未来 AI 向量检索（PgVector）奠定基础。

## What Changes
- 将 Django 数据库后端从 `django.db.backends.sqlite3` 切换为 `django.db.backends.postgresql`
- 安装并配置 PostgreSQL 18 及 PgVector 扩展
- 迁移现有数据（~35 张表，预估 500MB-2GB）
- 更新 `requirements.txt` 添加 `psycopg2-binary`
- 配置连接池、时区、超时等 PostgreSQL 优化参数
- 提供完整的数据验证、回滚和监控方案

## Impact
- 影响所有 Django 应用（system, cmdb, k8s_manager, script_manager, ai_ops）
- 影响部署配置（settings.py, .env, Docker Compose）
- 影响 CI/CD 和运维监控体系

## ADDED Requirements

### Requirement: PostgreSQL 环境准备
The system SHALL provide PostgreSQL 18 运行环境，并安装 PgVector、pg_trgm、btree_gin 扩展。

#### Scenario: Docker 开发环境
- **WHEN** 开发人员在本地启动项目
- **THEN** Docker Compose 自动拉起 postgres:18-alpine 容器
- **AND** 自动创建 aiops_db 数据库和 aiops_user 用户
- **AND** 自动安装 vector、pg_trgm、btree_gin 扩展

#### Scenario: 生产环境部署
- **WHEN** 在生产服务器部署
- **THEN** PostgreSQL 18 主节点按推荐配置运行（shared_buffers=4GB, max_connections=200）
- **AND** 配置 WAL 归档和自动清理

### Requirement: Django 数据库配置切换
The system SHALL 支持通过环境变量切换数据库后端，无需修改代码。

#### Scenario: 配置切换
- **WHEN** 设置 `DB_ENGINE=django.db.backends.postgresql` 及相关环境变量
- **THEN** Django 自动连接 PostgreSQL
- **AND** 保留 SQLite 配置作为 fallback（开发环境）

#### Scenario: 连接优化
- **WHEN** 使用 PostgreSQL 后端
- **THEN** 启用 CONN_MAX_AGE=60 连接复用
- **AND** 启用 CONN_HEALTH_CHECKS=True
- **AND** 设置 statement_timeout=30000

### Requirement: 数据迁移零丢失
The system SHALL 提供完整的数据迁移流程，确保所有历史数据完整迁移。

#### Scenario: 标准迁移流程
- **WHEN** 执行迁移脚本
- **THEN** 先执行 `dumpdata` 从 SQLite 导出 JSON
- **AND** 执行 `migrate` 在 PostgreSQL 创建空表结构
- **AND** 执行 `loaddata` 导入数据到 PostgreSQL
- **AND** 执行 `sqlsequencereset` 更新自增序列
- **AND** 所有表记录数与迁移前一致（误差 < 0.01%）

#### Scenario: 大数据量分批导入
- **WHEN** 数据量超过 10GB 或内存受限
- **THEN** 支持按模型分批导入
- **AND** 支持断点续传（进度文件记录）

### Requirement: 数据完整性验证
The system SHALL 提供自动化验证脚本，覆盖表记录数、外键完整性、加密字段、时区、JSONB 类型。

#### Scenario: 迁移后自动验证
- **WHEN** 运行 `post_migration_validation.py`
- **THEN** 验证所有核心表记录数
- **AND** 验证外键无孤立记录
- **AND** 验证 Fernet 加密字段可正常解密
- **AND** 验证 DateTimeField 带时区信息
- **AND** 验证 JSONField 升级为 JSONB
- **AND** 验证 IP 字段为 INET 类型

### Requirement: 回滚机制
The system SHALL 提供完整的回滚方案，可在迁移失败时快速恢复至 SQLite。

#### Scenario: 迁移过程中回滚
- **WHEN** loaddata 过程中发现问题
- **THEN** 停止当前操作
- **AND** 清理 PostgreSQL 中不完整数据
- **AND** 恢复 settings.py 指向 SQLite
- **AND** 重启服务，预计 5-10 分钟恢复

#### Scenario: 迁移完成后回滚
- **WHEN** 迁移完成后发现严重问题
- **THEN** 备份当前 PostgreSQL 数据
- **AND** 从备份恢复 SQLite 文件
- **AND** 恢复 SSH 日志目录
- **AND** 切换配置并重启服务，预计 <15 分钟

### Requirement: 性能优化
The system SHALL 在迁移完成后提供 PostgreSQL 专属优化索引和查询建议。

#### Scenario: 索引优化
- **WHEN** 迁移完成并验证通过
- **THEN** 创建 ServerMetric 复合索引 (server_id, created_at DESC)
- **AND** 创建最近数据部分索引 (created_at > NOW() - INTERVAL '7 days')
- **AND** 创建 HighRiskAudit 全文搜索 GIN 索引
- **AND** 创建 ChatMessage 会话索引

### Requirement: 监控集成
The system SHALL 集成 Prometheus + Grafana 监控 PostgreSQL 性能。

#### Scenario: 监控部署
- **WHEN** 部署监控栈
- **THEN** Prometheus 抓取 postgres_exporter 指标
- **AND** Grafana 展示连接数、查询延迟、缓存命中率
- **AND** 配置告警规则（连接数过高、慢查询、死锁）

## MODIFIED Requirements

### Requirement: 现有 Django Settings
- **修改前**: DATABASES 硬编码指向 SQLite
- **修改后**: DATABASES 从环境变量读取，支持 SQLite/PostgreSQL 双模式
- **兼容性**: 开发环境默认仍可用 SQLite，生产环境强制 PostgreSQL

## REMOVED Requirements
无移除需求。
