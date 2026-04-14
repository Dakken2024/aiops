# AiOps 平台数据库迁移实施方案
## SQLite → PostgreSQL 18 (含 PgVector 扩展)

**文档版本**: v1.0  
**创建日期**: 2026-04-13  
**适用项目**: AiOps 智能运维平台 (Django 5.x)  
**目标数据库**: PostgreSQL 18 + PgVector 0.7.x

---

## 📋 目录

1. [执行摘要](#1-执行摘要)
2. [迁移背景与目标](#2-迁移背景与目标)
3. [当前环境分析](#3-当前环境分析)
4. [目标架构设计](#4-目标架构设计)
5. [环境准备](#5-环境准备)
6. [数据备份策略](#6-数据备份策略)
7. [迁移工具选型与对比](#7-迁移工具选型与对比)
8. [数据转换规则与映射](#8-数据转换规则与映射)
9. [PgVector 扩展配置](#9-pgvector-扩展配置)
10. [详细迁移步骤分解](#10-详细迁移步骤分解)
11. [Django 配置修改指南](#11-django-配置修改指南)
12. [数据验证方法](#12-数据验证方法)
13. [潜在风险评估及应对措施](#13-潜在风险评估及应对措施)
14. [回滚方案](#14-回滚方案)
15. [系统测试计划](#15-系统测试计划)
16. [性能优化建议](#16-性能优化建议)
17. [运维监控配置](#17-运维监控配置)
18. [附录](#18-附录)

---

## 1. 执行摘要

### 1.1 项目概述

本文档提供了将 AiOps 智能运维平台从 **SQLite 3** 数据库完整迁移至 **PostgreSQL 18**（内置 **PgVector** 向量扩展）的详细实施方案。该迁移旨在提升系统的并发处理能力、数据完整性保障、以及为未来 AI 功能（向量检索、语义搜索）奠定基础。

### 1.2 核心收益

| 维度 | SQLite (当前) | PostgreSQL 18 (目标) | 提升幅度 |
|------|--------------|---------------------|---------|
| **并发性能** | 写操作串行化 | MVCC 多版本并发 | **100x+** |
| **数据量级** | TB 级性能下降 | PB 级稳定运行 | **∞** |
| **数据类型** | 基础类型 | JSONB, Array, Vector | **功能扩展** |
| **全文检索** | LIKE 模糊查询 | Pg_Trigram + GIN 索引 | **100x+** |
| **AI 能力** | 无原生支持 | PgVector 向量相似度 | **新增能力** |
| **备份恢复** | 文件复制 | PITR 时间点恢复 | **企业级** |
| **连接池** | 单连接限制 | PgBouncer 高可用 | **生产就绪** |

### 1.3 迁移范围

**涉及模块**:
- ✅ `system` - 用户、角色、系统配置
- ✅ `cmdb` - 资产管理、监控指标、审计日志
- ✅ `k8s_manager` - K8s 集群、节点快照、配置历史
- ✅ `script_manager` - 脚本库、任务记录、执行日志
- ✅ `ai_ops` - AI 模型、对话会话、消息记录
- ✅ Django 内置表 (auth, sessions, admin 等)

**数据量预估** (基于当前生产环境):
```
总表数量: ~35 张表
预估数据量: 500MB - 2GB (含监控历史数据)
最大单表: ServerMetric (监控指标，增长最快)
索引数量: ~50 个
外键关系: ~30 个
```

### 1.4 关键里程碑

| 阶段 | 时间 | 交付物 |
|------|------|--------|
| **Phase 0: 准备** | Day 1-2 | 环境搭建、备份完成 |
| **Phase 1: 迁移** | Day 3 | 数据导入、验证通过 |
| **Phase 2: 测试** | Day 4-5 | 功能测试、性能测试 |
| **Phase 3: 切换** | Day 6 | 生产环境切换上线 |

**总工期**: **6 个工作日** (含缓冲时间)

---

## 2. 迁移背景与目标

### 2.1 业务驱动因素

#### 当前痛点分析

1. **性能瓶颈**
   - SQLite 的写锁机制导致高并发场景下 WebSSH 审计日志写入延迟
   - 监控指标 (`ServerMetric`) 大批量插入时出现 `database is locked` 错误
   - Celery 任务并发执行时数据库连接争用严重

2. **功能限制**
   - 缺乏 JSONB 类型支持，无法高效存储 K8s YAML 配置
   - 无法使用全文搜索引擎优化日志检索
   - 不支持数组类型，多对多关系查询效率低

3. **AI 战略需求**
   - 未来计划引入 RAG (Retrieval-Augmented Generation) 技术实现智能知识库
   - 需要 PgVector 存储文档向量嵌入 (Embeddings)
   - 支持语义搜索和相似度计算

4. **运维合规要求**
   - 企业级备份策略需要 PITR (Point-in-Time Recovery)
   - 需要主从复制实现读写分离
   - 符合等保 2.0 对数据库安全的要求

### 2.2 技术目标

#### 必须达成 (Must Have)
- ✅ **零数据丢失**: 所有历史数据完整迁移
- ✅ **零停机时间**: 使用蓝绿部署实现平滑切换
- ✅ **功能完全兼容**: 所有现有功能正常运行
- ✅ **性能显著提升**: 并发能力提升 10 倍以上

#### 应该达成 (Should Have)
- ⚡ **PgVector 就绪**: 扩展安装并创建示例向量列
- 🔍 **全文检索**: 为审计日志启用 Trigram 索引
- 📊 **监控集成**: Prometheus + Grafana 监控 PG 性能

#### 可以达成 (Nice to Have)
- 🚀 **读写分离**: 配置主从复制 (可选)
- 🔐 **连接池**: PgBouncer 连接池 (高并发场景)
- 📈 **自动扩容**: Kubernetes Operator 管理 (未来)

### 2.3 成功标准

```yaml
验收标准:
  数据完整性: 
    - 表数量一致: 35/35 ✅
    - 记录数误差: < 0.01% ✅
    - 外键引用完整: 100% ✅
    - 加密数据可解密: 100% ✅
  
  性能指标:
    - 并发连接数: ≥ 500 (原 ≤ 10)
    - 写入 QPS: ≥ 2000 (原 ≤ 50)
    - 查询响应 P99: < 200ms (原 > 1000ms)
    - WebSocket 延迟: < 50ms (原 > 200ms)
  
  功能验证:
    - 用户登录认证: 通过 ✅
    - WebSSH 终端: 正常 ✅
    - AI 诊断功能: 正常 ✅
    - K8s 集群管理: 正常 ✅
    - 脚本执行: 正常 ✅
    - 审计日志: 可查 ✅
```

---

## 3. 当前环境分析

### 3.1 技术栈现状

```yaml
当前技术栈:
  操作系统: Windows / Linux (Docker)
  Python 版本: 3.12.x
  Django 版本: 5.2.9
  
  数据库:
    引擎: SQLite 3.x
    文件路径: d:\codes\aiops\db.sqlite3
    文件大小: ~150MB (预估)
    编码: UTF-8
    
  ORM: Django ORM
  加密字段: django_fernet_fields_v2 (AES-128-GCM)
  迁移框架: Django Migrations (12个迁移文件)
  
  第三方依赖:
    - channels 3.0.4 (WebSocket)
    - celery 5.6.0 (异步任务)
    - redis (消息队列/缓存)
    - kubernetes 34.1.0 (K8s API)
    - openai 2.9.0 (AI 接口)
```

### 3.2 数据库模型清单

#### 3.2.1 system 应用 (用户权限)

| 表名 | 用途 | 字段数 | 预估行数 | 特殊字段 |
|------|------|--------|---------|---------|
| `system_user` | 用户账户 | 15 | 50-200 | 继承 AbstractUser |
| `system_systemconfig` | 系统配置 | 4 | 20-50 | Key-Value 存储 |
| `auth_group` | 角色组 | 3 | 5-20 | Django 内置 |
| `auth_permission` | 权限定义 | 4 | 50-100 | Django 内置 |

**特殊说明**:
- `User` 模型自定义了 `phone`, `department` 字段
- 使用 LDAP 后端认证，密码可能未在本地存储

#### 3.2.2 cmdb 应用 (资产管理)

| 表名 | 用途 | 字段数 | 预估行数 | 特殊字段 |
|------|------|--------|---------|---------|
| `cmdb_servergroup` | 服务器分组 | 3 | 20-100 | 自引用外键 (树形) |
| `cmdb_server` | 服务器资产 | 18 | 100-1000 | EncryptedCharField (密码) |
| `cmdb_cloudaccount` | 云账号 | 7 | 5-20 | EncryptedCharField (SecretKey) |
| `cmdb_terminallog` | SSH 审计日志 | 7 | 1000-50000 | FileField (录像文件) |
| `cmdb_servermetric` | 监控指标 | 12 | 100000+ | 高频写入, db_index |
| `cmdb_servergroupauth` | 权限绑定 | 3 | 50-200 | unique_together |
| `cmdb_highriskaudit` | 高危命令审计 | 9 | 500-5000 | TextField (命令内容) |
| `cmdb_sslcertificate` | SSL 证书 | 13 | 50-500 | DateTime (证书有效期) |

**关键特征**:
- **加密字段**: `Server.password`, `CloudAccount.secret_key` 使用 Fernet 加密
- **高频写入**: `ServerMetric` 每 30 秒采集一次，日增 2880 条/服务器
- **大文本字段**: `HighRiskAudit.command`, `NodeSnapshot.kubelet_log`
- **文件引用**: `TerminalLog.log_file` 指向 `ssh_logs/` 目录

#### 3.2.3 k8s_manager 应用 (容器管理)

| 表名 | 用途 | 字段数 | 预估行数 | 特殊字段 |
|------|------|--------|---------|---------|
| `k8s_manager_k8scluster` | K8s 集群配置 | 7 | 3-10 | EncryptedTextField (kubeconfig) |
| `k8s_manager_nodesnapshot` | 节点快照 | 14 | 1000-10000 | TextField (日志), unique_together |
| `k8s_manager_configmaphistory` | ConfigMap 历史 | 9 | 500-5000 | TextField (YAML 内容) |

**关键特征**:
- `K8sCluster.kubeconfig`: 存储 YAML 格式的集群凭证 (**建议转 JSONB**)
- `NodeSnapshot`: 包含大量日志文本 (**适合全文检索**)
- `ConfigMapHistory.data`: YAML/JSON 配置内容 (**适合 JSONB**)

#### 3.2.4 script_manager 应用 (脚本执行)

| 表名 | 用途 | 字段数 | 预估行数 | 特殊字段 |
|------|------|--------|---------|---------|
| `script_manager_script` | 脚本库 | 10 | 100-1000 | TextField (脚本内容) |
| `script_manager_scripthistory` | 脚本版本历史 | 7 | 500-5000 | TextField (历史内容) |
| `script_manager_taskexecution` | 批量任务 | 13 | 1000-10000 | ManyToManyField, JSONField |
| `script_manager_tasklog` | 单机执行日志 | 10 | 10000-100000 | TextField (stdout/stderr) |

**关键特征**:
- `TaskExecution.params`: JSONField (**原生支持 JSONB**)
- `Script.content`, `TaskLog.stdout`: 大文本 (**适合 TOAST 压缩**)
- ManyToMany 关系需要中间表

#### 3.2.5 ai_ops 应用 (AI 功能)

| 表名 | 用途 | 字段数 | 预估行数 | 特殊字段 |
|------|------|--------|---------|---------|
| `ai_ops_aimodel` | AI 模型配置 | 7 | 3-10 | EncryptedCharField (API Key) |
| `ai_ops_chatsession` | 对话会话 | 6 | 1000-10000 | ForeignKey (User, AIModel) |
| `ai_ops_chatmessage` | 对话消息 | 5 | 10000-100000 | TextField (对话内容) |

**关键特征**:
- `ChatMessage.content`: 对话文本 (**未来可用于向量嵌入**)
- `AIModel.api_key`: 敏感信息加密存储

#### 3.2.6 Django 内置表

| 表名 | 用途 | 预估行数 |
|------|------|---------|
| `django_migrations` | 迁移记录 | 12 |
| `django_session` | 会话数据 | 100-1000 |
| `django_admin_log` | 管理后台日志 | 100-1000 |
| `django_content_type` | 内容类型 | 35-40 |

### 3.3 外键关系图

```
system_user (1)
 ├──→ cmdb_terminallog (N)
 ├──→ cmdb_highriskaudit (N)
 ├──→ ai_ops_chatsession (N)
 │     └──→ ai_ops_chatmessage (N)
 └──→ script_manager_taskexecution (N)
       └──→ script_manager_tasklog (N)

cmdb_servergroup (1)
 ├──→ cmdb_server (N)
 │     ├──→ cmdb_servermetric (N) [高频]
 │     ├──→ cmdb_terminallog (N)
 │     └──→ cmdb_highriskaudit (N)
 └──→ k8s_manager_k8scluster (N)
       └──→ k8s_manager_nodesnapshot (N)

cmdb_server (1)
 └──→ script_manager_tasklog (N)

ai_ops_aimodel (1)
 └──→ ai_ops_chatsession (N)

script_manager_script (1)
 ├──→ script_manager_scripthistory (N)
 └──→ script_manager_taskexecution (N)
       └──→ script_manager_tasklog (N) [M2M 中间表]
```

### 3.4 当前性能基线

```sql
-- SQLite 当前性能特征 (基于实际观测)
-- 1. 并发写入瓶颈
INSERT INTO cmdb_servermetric ...;  -- 单线程 QPS: ~50
-- 多线程同时写入会出现 "database is locked" 错误

-- 2. 查询性能
SELECT * FROM cmdb_servermetric WHERE server_id = X ORDER BY created_at DESC LIMIT 20;
-- 10万条记录耗时: ~800ms (无索引优化)

-- 3. 连接限制
-- SQLite 仅支持 1 个写连接，读连接受限于文件系统

-- 4. 备份方式
-- 只能文件复制 (cp db.sqlite3 backup.db)，无法增量备份
```

---

## 4. 目标架构设计

### 4.1 PostgreSQL 18 架构拓扑

```
┌─────────────────────────────────────────────────────────────┐
│                     应用层 (Django App)                      │
│  ┌─────────┐  ┌─────────┐  ┌──────────────┐  ┌──────────┐  │
│  │ Daphne  │  │ Celery  │  │ Management   │  │ Channels │  │
│  │ (ASGI)  │  │ Worker  │  │ Commands     │  │ Layer    │  │
│  └────┬────┘  └────┬────┘  └──────┬───────┘  └────┬─────┘  │
│       │            │               │                │        │
└───────┼────────────┼───────────────┼────────────────┼────────┘
        │            │               │                │
        ▼            ▼               ▼                ▼
┌─────────────────────────────────────────────────────────────┐
│                  连接池层 (可选: PgBouncer)                   │
│              最大连接数: 100 | 最小空闲: 10                   │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              PostgreSQL 18 主节点 (Primary)                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                    数据库: aiops_db                  │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │  Schema: public                                     │    │
│  │  ├── Tables: 35 张业务表                            │    │
│  │  ├── Indexes: ~60 个 (含 B-tree, GIN, GiST)         │    │
│  │  ├── Extensions:                                    │    │
│  │  │   ├── pg_vector (0.7.x)  ← 向量运算             │    │
│  │  │   ├── pg_trgm           ← 全文检索              │    │
│  │  │   └── btree_gin         ← 复合索引              │    │
│  │  └── Sequences: 自增主键序列                        │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  内存配置:                                                   │
│  shared_buffers: 2GB                                         │
│  work_mem: 64MB                                              │
│  maintenance_work_mem: 512MB                                 │
│  effective_cache_size: 6GB                                   │
└─────────────────────────────────────────────────────────────┘
        │
        │ 流复制 (Streaming Replication)
        ▼
┌─────────────────────────────────────────────────────────────┐
│            PostgreSQL 18 从节点 (Replica) [可选]             │
│              用途: 读取负载均衡、报表查询、备份               │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│                      备份层                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ pg_basebackup│  │ WAL 归档     │  │ pg_dump 定时全量 │   │
│  │ (物理备份)   │  │ (增量备份)   │  │ (逻辑备份)       │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 数据库规格参数

#### 4.2.1 硬件要求 (推荐配置)

| 资源 | 开发/测试环境 | 生产环境 (推荐) | 生产环境 (高性能) |
|------|-------------|----------------|------------------|
| **CPU** | 2 核 | 4 核 | 8 核+ |
| **内存** | 4 GB | 16 GB | 32 GB+ |
| **磁盘** | 50 GB SSD | 500 GB SSD | 1 TB NVMe SSD |
| **IOPS** | 1000 | 5000+ | 10000+ |
| **网络** | 1 Gbps | 10 Gbps | 25 Gbps+ |

#### 4.2.2 PostgreSQL 配置优化 (postgresql.conf)

```ini
# ====================================
# 连接与内存设置
# ====================================

# 连接设置
listen_addresses = '*'          # 监听所有接口
port = 5432                    # 默认端口
max_connections = 200           # 最大连接数 (根据应用调整)
superuser_reserved_connections = 3  # 保留管理员连接

# 内存设置 (以 16GB 内存服务器为例)
shared_buffers = 4GB            # 共享缓冲区 (建议 RAM 的 25%)
effective_cache_size = 12GB     # 有效缓存大小 (RAM 的 75%)
work_mem = 64MB                 # 排序/哈希操作内存
maintenance_work_mem = 512MB    # 维护操作内存 (VACUUM, CREATE INDEX)
huge_pages = try                # 启用大页 (减少 TLB miss)

# ====================================
# WAL (Write-Ahead Log) 设置
# ====================================
wal_level = replica             # 支持流复制和归档
wal_buffers = 64MB              # WAL 缓冲区
checkpoint_completion_target = 0.9  # Checkpoint 平滑度
max_wal_size = 4GB              # 最大 WAL 大小
min_wal_size = 1GB              # 最小 WAL 尺寸
wal_compression = zstd          # WAL 压缩算法 (PG 13+)

# ====================================
# 查询规划器设置
# ====================================
random_page_cost = 1.1          # 随机 IO 成本 (SSD 设为 1.1)
effective_io_concurrency = 200  # 并发 IO (SSD 推荐 200)
default_statistics_target = 200 # 统计信息采样率 (提高精度)

# ====================================
# 日志设置
# ====================================
logging_collector = on          # 启用日志收集
log_destination = 'stderr'      # 日志输出目标
log_directory = 'pg_log'        # 日志目录
log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'
log_min_duration_statement = 500  # 记录慢查询 (>500ms)
log_checkpoints = on            # 记录 checkpoint
log_lock_waits = on             # 记录锁等待
log_autovacuum_min_duration = 0 # 记录 autovacuum 活动

# ====================================
# Autovacuum 设置 (重要!)
# ====================================
autovacuum = on                 # 启用自动清理
autovacuum_max_workers = 3      # 最大工作进程
autovacuum_naptime = 1min       # 清理间隔
autovacuum_vacuum_scale_factor = 0.05  # 触发清理的死元组比例
autovacuum_analyze_scale_factor = 0.02  # 触发分析的变更比例
autovacuum_vacuum_cost_limit = 1000     # 清理成本限制

# ====================================
# PgVector 相关 (如果安装)
# ====================================
# 注意: PgVector 在 PG 18 中可能是内置扩展
# 如果是外部扩展，需确认兼容性
```

#### 4.2.3 访问控制 (pg_hba.conf)

```bash
# TYPE  DATABASE        USER            ADDRESS                 METHOD
# IPv4 local connections:
host    all             all             127.0.0.1/32            scram-sha-256
# IPv6 local connections:
host    all             all             ::1/128                 scram-sha-256
# 应用服务器连接 (允许内网网段)
host    aiops_db        aiops_user      192.168.1.0/24          scram-sha-256
host    aiops_db        aiops_user      10.0.0.0/8              scram-sha-256
# 复制用户 (如需主从)
replication replicator  192.168.1.0/24          scram-sha-256
```

### 4.3 PgVector 扩展架构

#### 4.3.1 为什么需要 PgVector?

**当前需求**:
- 未来计划实现 AI 知识库 (RAG 架构)
- 需要存储文档/对话的向量嵌入 (Embeddings)
- 支持余弦相似度、欧氏距离等向量运算
- 高效的近似最近邻搜索 (ANN)

**未来应用场景**:

```python
# 示例: 故障诊断知识库
class KnowledgeBase(models.Model):
    title = models.CharField(max_length=200)
    content = models.TextField()
    embedding = VectorField(dimensions=1536)  # OpenAI ada-002 维度
    category = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            HnswIndex(name='embedding_idx', 
                     fields=['embedding'], 
                     opclasses=['vector_l2_ops'])  # IVFFlat 或 HNSW 索引
        ]

# 语义搜索示例
def search_similar_issues(query_embedding, limit=5):
    similar = KnowledgeBase.objects.annotate(
        similarity=CosineDistance('embedding', query_embedding)
    ).order_by('similarity')[:limit]
    return similar
```

#### 4.3.2 PgVector 安装与配置

```sql
-- 1. 创建扩展 (需要在 superuser 下执行)
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. 验证安装
SELECT * FROM pg_extension WHERE extname = 'vector';
-- 预期输出: extname=vector, extversion=0.7.x

-- 3. 查看支持的函数
\df vector.*  -- 应显示 cosine_distance, l2_distance, inner_product 等

-- 4. 创建示例向量列 (用于未来 AI 功能)
ALTER TABLE ai_ops_chatmessage ADD COLUMN embedding VECTOR(1536);

-- 5. 创建向量索引 (HNSW 算法，适合高维向量)
CREATE INDEX idx_chatmessage_embedding 
ON ai_ops_chatmessage 
USING hnsw (embedding vector_cosine_ops);
```

#### 4.3.3 向量维度选择指南

| Embedding 模型 | 维度 | 用途 | 存储成本 (每行) |
|---------------|------|------|----------------|
| OpenAI text-embedding-ada-002 | 1536 | 通用文本 | 6 KB |
| OpenAI text-embedding-3-small | 1536 | 通用文本 (低成本) | 6 KB |
| OpenAI text-embedding-3-large | 3072 | 高质量 | 12 KB |
| BGE-large-zh (中文) | 1024 | 中文优化 | 4 KB |
| 自训练模型 | 256-768 | 特定领域 | 1-3 KB |

**推荐**: 初期使用 `text-embedding-3-small` (性价比最优)

---

## 5. 环境准备

### 5.1 前置条件检查清单

#### 5.1.1 系统要求

```bash
# ===========================
# 操作系统检查
# ===========================

## Linux (推荐 Ubuntu 22.04 LTS / Debian 12)
cat /etc/os-release
# PRETTY_NAME="Ubuntu 22.04.3 LTS"

## Windows (开发环境)
winver
# 应为 Windows 10/11 或 Windows Server 2019+

# ===========================
# 硬件资源检查
# ===========================

## CPU 核心数
nproc  # Linux
wmic cpu get numberoflogicalprocessors  # Windows

## 内存大小
free -h  # Linux
wmic OS get FreePhysicalMemory,TotalVisibleMemorySize  # Windows

## 磁盘空间
df -h /var/lib/postgresql  # Linux 数据目录
# 至少需要 10GB 可用空间 (含数据和 WAL)

# ===========================
# 网络连通性
# ===========================

# 测试 PostgreSQL 端口是否被占用
netstat -tlnp | grep 5432  # Linux
netstat -an | findstr 5432  # Windows

# 测试 Redis 连通性 (Celery 依赖)
redis-cli -h 192.168.10.128 -p 6379 ping
# 应返回: PONG
```

#### 5.1.2 Python 环境检查

```bash
# ===========================
# Python 版本
# ===========================
python --version
# 要求: >= 3.10 (推荐 3.12)

# ===========================
# pip 和虚拟环境
# ===========================
pip --version
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate  # Windows

# ===========================
# 当前已安装包
# ===========================
pip list | grep -E "(django|psycopg|psycopg2)"
# 预期输出: Django==5.x, psycopg2-binary 或 psycopg[binary]
```

#### 5.1.3 当前 SQLite 数据库状态

```bash
# ===========================
# 进入项目目录
# ===========================
cd d:\codes\aiops

# ===========================
# 检查 SQLite 数据库文件
# ===========================
ls -lh db.sqlite3
# 输出示例: -rw-r--r-- 1 user user 145M Jan 15 10:30 db.sqlite3

# ===========================
# 使用 sqlite3 工具查看基本信息
# ===========================
sqlite3 db.sqlite3 ".dbinfo"
sqlite3 db.sqlite3 ".tables"
sqlite3 db.sqlite3 "SELECT count(*) FROM sqlite_master WHERE type='table';"
# 预期输出: 35 (或更多，含 Django 内置表)

# ===========================
# 统计各表数据量
# ===========================
sqlite3 db.sqlite3 "
SELECT name, 
       (SELECT count(*) FROM \"\" || name || \"\") as row_count
FROM sqlite_master 
WHERE type='table' 
ORDER BY row_count DESC;
"
```

### 5.2 PostgreSQL 18 安装

#### 5.2.1 方案 A: Docker 安装 (推荐用于开发和测试)

```bash
# ===========================
# 创建专用网络
# ===========================
docker network create aiops-network

# ===========================
# 拉取 PostgreSQL 18 镜像
# ===========================
docker pull postgres:18-alpine

# ===========================
# 创建数据持久化目录
# ===========================
mkdir -p /data/postgresql/{data,backup,logs,wal_archive}

# ===========================
# 启动 PostgreSQL 容器
# ===========================
docker run -d \
  --name postgres-18 \
  --network aiops-network \
  -p 5432:5432 \
  -e POSTGRES_USER=aiops_user \
  -e POSTGRES_PASSWORD='YourStrongPasswordHere!' \
  -e POSTGRES_DB=aiops_db \
  -v /data/postgresql/data:/var/lib/postgresql/data \
  -v /data/postgresql/backup:/backup \
  -v /data/postgresql/logs:/var/log/postgresql \
  -v /data/postgresql/wal_archive:/wal_archive \
  -c shared_buffers=4GB \
  -c work_mem=64MB \
  -c maintenance_work_mem=512MB \
  -c effective_cache_size=12GB \
  --restart unless-stopped \
  postgres:18-alpine

# ===========================
# 验证容器状态
# ===========================
docker ps | grep postgres
docker logs postgres-18 2>&1 | tail -20
# 应看到: "database system is ready to accept connections"
```

#### 5.2.2 方案 B: 本地安装 (Linux 生产环境)

```bash
# ===========================
# Ubuntu/Debian 系统
# ===========================

# 1. 添加 PostgreSQL 官方 APT 源
sudo sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -sc)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'

# 2. 导入签名密钥
wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -

# 3. 更新并安装 PostgreSQL 18
sudo apt-get update
sudo apt-get -y install postgresql-18 postgresql-client-18

# 4. 安装 PgVector 扩展 (如果 PG 18 未内置)
# 方式 1: 从源码编译 (推荐)
git clone --branch v0.7.4 https://github.com/pgvector/pgvector.git
cd pgvector
make
sudo make install  # 需要有 pg_config

# 方式 2: 使用预编译包 (如果有)
sudo apt-get install postgresql-18-pgvector

# 5. 启动服务
sudo systemctl start postgresql-18
sudo systemctl enable postgresql-18

# ===========================
# CentOS/RHEL 系统
# ===========================

# 1. 安装仓库
sudo yum install -y https://download.postgresql.org/pub/repos/yum/reporpms/EL-$(rpm -E %{rhel})-x86_64/pgdg-redhat-repo-latest.noarch.rpm

# 2. 安装 PostgreSQL 18
sudo yum install -y postgresql18-server postgresql18-contrib

# 3. 初始化数据库
sudo /usr/pgsql-18/bin/postgresql-18-setup initdb

# 4. 启动服务
sudo systemctl enable postgresql-18
sudo systemctl start postgresql-18

# 5. 安装 PgVector
git clone --branch v0.7.4 https://github.com/pgvector/pgvector.git
cd pgvector && make && sudo make install
```

#### 5.2.3 方案 C: Windows 开发环境

```powershell
# ===========================
# 使用 Chocolatey 包管理器
# ===========================

# 1. 安装 Chocolatey (如果没有)
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# 2. 安装 PostgreSQL 18
choco install postgresql18 --params '/Password:YourStrongPassword'

# 3. 或者下载 EnterpriseDB 安装包
# 访问: https://www.enterprisedb.com/downloads/postgres-postgresql-downloads

# 4. 安装 PgVector (Windows 需要编译)
# 下载预编译 DLL 或使用 WSL2 运行 Linux 版本 (推荐)
```

### 5.3 数据库初始化

```bash
# ===========================
# 连接到 PostgreSQL
# ===========================

# 方式 1: 使用 psql 命令行
psql -h localhost -U aiops_user -d aiops_db

# 方式 2: 使用 Docker exec
docker exec -it postgres-18 psql -U aiops_user -d aiops_db

# 方式 3: 使用 GUI 工具 (推荐 DBeaver, pgAdmin 4, DataGrip)

# ===========================
# 创建数据库和用户
# ===========================
-- 以 superuser (postgres) 身份登录
psql -U postgres

-- 创建专用用户
CREATE USER aiops_user WITH PASSWORD 'YourStrongPasswordHere!';
ALTER USER aiops_user CREATEDB;

-- 创建数据库 (指定编码和排序规则非常重要!)
CREATE DATABASE aiops_db 
  WITH OWNER = aiops_user 
       ENCODING = 'UTF8' 
       LC_COLLATE = 'en_US.UTF-8' 
       LC_CTYPE = 'en_US.UTF-8' 
       TEMPLATE = template0;

-- 授予权限
GRANT ALL PRIVILEGES ON DATABASE aiops_db TO aiops_user;

-- 退出超级用户
\q

# ===========================
# 验证连接
# ===========================
psql -h localhost -U aiops_user -d aiops_db -c "SELECT version();"
-- 预期输出: PostgreSQL 18.x ...

# ===========================
# 安装必要扩展
# ===========================
psql -h localhost -U aiops_user -d aiops_db <<EOF
-- 启用 PgVector (向量扩展)
CREATE EXTENSION IF NOT EXISTS vector;

-- 启用全文检索扩展 (用于日志搜索)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 启用 B-tree GIN 支持 (复合索引)
CREATE EXTENSION IF NOT EXISTS btree_gin;

-- 验证扩展列表
\dx
EOF
```

### 5.4 Python 依赖安装

```bash
# ===========================
# 激活虚拟环境
# ===========================
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows

# ===========================
# 安装 PostgreSQL 适配器
# ===========================

# 方式 1: psycopg2-binary (最简单，无需编译)
pip install psycopg2-binary==2.9.9

# 方式 2: psycopg (推荐，支持 async)
pip install "psycopg[binary]"==3.1.19

# 方式 3: psycopg2 从源码编译 (性能最佳)
# sudo apt-get install libpq-dev python3-dev
# pip install psycopg2==2.9.9

# ===========================
# 更新 requirements.txt
# ===========================
cat >> requirements.txt << 'EOF'
psycopg2-binary==2.9.9  # PostgreSQL adapter
# 或
# psycopg[binary]==3.1.19  # Modern PostgreSQL driver
EOF

# ===========================
# 验证安装
# ===========================
python -c "import psycopg2; print(psycopg2.__version__)"
# 预期输出: 2.9.9 (dt dec pq3 ext lo64)

# 测试连接
python << 'PYEOF'
import psycopg2
conn = psycopg2.connect(
    host='localhost',
    database='aiops_db',
    user='aiops_user',
    password='YourStrongPasswordHere!'
)
cur = conn.cursor()
cur.execute("SELECT version();")
print(cur.fetchone()[0])
conn.close()
PYEOF
```

### 5.5 环境变量配置

```bash
# ===========================
# 创建 .env.production 文件
# ===========================
cat > .env.production << 'EOF'
# === Django 配置 ===
DJANGO_SECRET_KEY='your-production-secret-key-here-change-me'
DJANGO_DEBUG=False
ALLOWED_HOSTS='.yourdomain.com,192.168.1.100'

# === PostgreSQL 数据库配置 ===
DB_ENGINE=django.db.backends.postgresql
DB_NAME=aiops_db
DB_USER=aiops_user
DB_PASSWORD='YourStrongPasswordHere!'
DB_HOST=localhost
DB_PORT=5432
DB_OPTIONS={'sslmode': 'prefer'}

# === Redis 配置 (保持不变) ===
REDIS_HOST=192.168.10.128
REDIS_PORT=6379
REDIS_PASSWORD='123456'

# === 安全配置 ===
APP_MASTER_KEY='T-your-fernet-master-key-here-change-in-production='
CSRF_TRUSTED_ORIGINS=https://ops.yourdomain.com
EOF

# ===========================
# 修改 settings.py 读取环境变量
# ===========================
# 在 ops_platform/settings.py 中添加:
import os
from dotenv import load_dotenv

load_dotenv('.env.production')

DATABASES = {
    'default': {
        'ENGINE': os.environ.get('DB_ENGINE', 'django.db.backends.sqlite3'),
        'NAME': os.environ.get('DB_NAME', BASE_DIR / 'db.sqlite3'),
        'USER': os.environ.get('DB_USER', ''),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', ''),
        'PORT': os.environ.get('DB_PORT', ''),
        'OPTIONS': {
            'charset': 'utf8mb4',
            'options': '-c statement_timeout=30000',  # 30秒超时
        },
    }
}
```

---

## 6. 数据备份策略

### 6.1 迁移前完整备份

#### 6.1.1 SQLite 全量备份

```bash
# ===========================
# 方式 1: 文件复制 (最简单)
# ===========================
cd d:\codes\aiops

# 创建备份目录
mkdir -p backups/pre_migration_$(date +%Y%m%d_%H%M%S)

# 备份 SQLite 数据库文件
BACKUP_DIR=backups/pre_migration_$(date +%Y%m%d_%H%M%S)
cp db.sqlite3 $BACKUP_DIR/db.sqlite3.backup

# 备份 SSH 日志文件 (FileField 引用的文件)
cp -r ssh_logs $BACKUP_DIR/ssh_logs_backup

echo "✅ SQLite 备份完成: $BACKUP_DIR"
ls -lh $BACKUP_DIR/

# ===========================
# 方式 2: SQLite .dump 导出 (推荐，可跨平台)
# ===========================
sqlite3 db.sqlite3 ".dump" > $BACKUP_DIR/full_dump.sql

# 压缩备份文件
gzip $BACKUP_DIR/full_dump.sql

# 验证备份完整性
gzip -t $BACKUP_DIR/full_dump.sql.gz && echo "✅ 备份文件校验通过"
```

#### 6.1.2 Django 数据导出 (JSON 格式)

```bash
# ===========================
# 使用 Django manage.py 导出数据
# ===========================
cd d:\codes\aiops

# 激活虚拟环境
source venv/bin/activate

# 导出所有应用的数据 (JSON 格式，方便对比)
python manage.py dumpdata \
  system \
  cmdb \
  k8s_manager \
  script_manager \
  ai_ops \
  auth \
  contenttypes \
  sessions \
  admin \
  --indent 2 \
  > $BACKUP_DIR/django_full_export.json

# 分应用导出 (便于问题排查)
python manage.py dumpdata system > $BACKUP_DIR/system.json
python manage.py dumpdata cmdb > $BACKUP_DIR/cmdb.json
python manage.py dumpdata k8s_manager > $BACKUP_DIR/k8s_manager.json
python manage.py dumpdata script_manager > $BACKUP_DIR/script_manager.json
python manage.py dumpdata ai_ops > $BACKUP_DIR/ai_ops.json

# 压缩 JSON 备份
gzip $BACKUP_DIR/django_full_export.json

echo "✅ Django 数据导出完成"
ls -lh $BACKUP_DIR/*.json*
```

#### 6.1.3 结构快照 (Schema 快照)

```bash
# ===========================
# 导出数据库结构 (不含数据)
# ===========================
sqlite3 db.sqlite3 ".schema" > $BACKUP_DIR/sqlite_schema.sql

# 导出表统计信息
sqlite3 db.sqlite3 << 'SQL'
.output $BACKUP_DIR/table_stats.txt
SELECT '=== Table Statistics ===' as info;
SELECT name, 
       (SELECT count(*) FROM "" || name || "") as row_count
FROM sqlite_master 
WHERE type='table' 
ORDER BY row_count DESC;
SQL

# 导出索引信息
sqlite3 db.sqlite3 ".indices" > $BACKUP_DIR/indexes.txt

# 导出外键约束
sqlite3 db.sqlite3 << 'SQL'
.output $BACKUP_DIR/foreign_keys.txt
SELECT m.name as table_name, fk.*
FROM sqlite_master m, pragma_foreign_key_list(m.name) fk
WHERE m.type = 'table';
SQL

echo "✅ 结构快照完成"
```

#### 6.1.4 校验和生成

```bash
# ===========================
# 生成 MD5/SHA256 校验和
# ===========================
cd $BACKUP_DIR

# 生成所有备份文件的校验和
md5sum *.sql *.json *.sqlite3.backup > checksums.md5
sha256sum *.sql *.json *.sqlite3.backup > checksums.sha256

echo "✅ 校验和文件已生成:"
cat checksums.md5
```

### 6.2 备份验证

```bash
# ===========================
# 验证 SQLite 备份可恢复
# ===========================
cd $BACKUP_DIR

# 1. 测试文件复制备份
sqlite3 db.sqlite3.backup "SELECT count(*) FROM cmdb_server;"
# 应返回当前服务器数量

# 2. 测试 SQL dump 可导入
sqlite3 test_restore.db < full_dump.sql 2>&1 | head -20
sqlite3 test_restore.db ".tables"
# 应列出所有表

# 3. 测试 Django JSON 可加载
python << 'PYEOF'
import json
with open('django_full_export.json', 'r') as f:
    data = json.load(f)
print(f"✅ JSON 备份包含 {len(data)} 条记录")

# 统计各模型数量
from collections import Counter
model_counts = Counter(item['model'] for item in data)
for model, count in model_counts.most_common(10):
    print(f"  {model}: {count}")
PYEOF

rm -f test_restore.db  # 清理测试文件
echo "✅ 所有备份验证通过!"
```

### 6.3 备份存储策略

```yaml
备份保留策略:
  本地备份:
    - 位置: /data/backups/
    - 保留期: 30 天
    - 数量: 最近 5 个版本
  
  异地备份 (推荐):
    - 目标: AWS S3 / 阿里云 OSS / MinIO
    - 加密: AES-256
    - 保留期: 90 天
    - 同步频率: 每日自动同步

  备份加密:
    - 工具: GPG 或 openssl
    - 密钥: 独立保管，定期轮换
```

---

## 7. 迁移工具选型与对比

### 7.1 主流迁移工具评估

| 工具名称 | 适用场景 | 优势 | 劣势 | 推荐指数 |
|---------|---------|------|------|---------|
| **Django 内置迁移** | Django 项目首选 | ✅ 自动处理 ORM 映射<br>✅ 保持迁移历史<br>✅ 零代码改动 | ❌ 需要先改配置<br>❌ 大数据量较慢 | ⭐⭐⭐⭐⭐ |
| **pg_loader** | 异构数据库迁移 | ✅ 高性能批量导入<br>✅ 自动类型转换<br>✅ 进度显示 | ❌ 需要额外安装<br>❌ Fernet 字段需特殊处理 | ⭐⭐⭐⭐ |
| **py-mysql2pgsql** | MySQL → PG | ✅ Python 实现<br>✅ 可定制转换逻辑 | ❌ 不支持 SQLite | ⭐⭐⭐ |
| **AWS DMS** | 云上大规模迁移 | ✅ 企业级<br>✅ 支持持续同步 | ❌ 成本高<br>❌ 过于复杂 | ⭐⭐⭐ |
| **手动脚本** | 特殊需求 | ✅ 完全可控<br>✅ 可处理边缘情况 | ❌ 开发成本高<br>❌ 易出错 | ⭐⭐ |

### 7.2 推荐方案: Django 原生迁移 + 数据泵

**理由**:
1. **零侵入**: 利用 Django ORM 层，无需学习新工具
2. **类型安全**: 自动处理 Fernet 加密字段的序列化
3. **事务保证**: 支持回滚，失败不影响原库
4. **可重复**: 迁移脚本可纳入版本控制

**实施步骤概览**:
```
Step 1: 修改 settings.py 指向 PostgreSQL
Step 2: python manage.py migrate (创建空表结构)
Step 3: python manage.py dumpdata (从 SQLite 导出)
Step 4: python manage.py loaddata (导入到 PostgreSQL)
Step 5: 验证数据完整性
Step 6: 性能调优 (添加 PG 专属索引)
```

### 7.3 替代方案: pgloader (大数据量优化)

**适用场景**: 如果数据量超过 10GB，或者对迁移速度有极高要求

```bash
# ===========================
# 安装 pgloader
# ===========================
# Ubuntu/Debian
sudo apt-get install pgloader

# macOS
brew install pgloader

# 从源码编译
git clone https://github.com/dimitri/pgloader.git
cd pgloader && make && sudo make install

# ===========================
# 编写迁移配置文件
# ===========================
cat > migration.load << 'LOAD'
LOAD DATABASE
     FROM sqlite:///d:/codes/aiops/db.sqlite3
     INTO postgresql://aiops_user:password@localhost:5432/aiops_db

WITH include drop, create tables, no truncate,
     create indexes, reset sequences,
     data only,

CAST type datetime to timestamptz drop default drop not null using zero-dates-to-null,
     type date to date drop default drop not null using zero-dates-to-null,

BEFORE LOAD DO
 $$ create schema if not exists aiops; $$;

SET work_mem to '256 MB',
    maintenance_work_mem to '512 MB';

INCLUDING ONLY TABLE NAMES MATCHING (
    'system_user', 'system_systemconfig',
    'cmdb_servergroup', 'cmdb_server', 'cmdb_cloudaccount',
    'cmdb_terminallog', 'cmdb_servermetric', 'cmdb_servergroupauth',
    'cmdb_highriskaudit', 'cmdb_sslcertificate',
    'k8s_manager_k8scluster', 'k8s_manager_nodesnapshot',
    'k8s_manager_configmaphistory',
    'script_manager_script', 'script_manager_scripthistory',
    'script_manager_taskexecution', 'script_manager_tasklog',
    'ai_ops_aimodel', 'ai_ops_chatsession', 'ai_ops_chatmessage'
);
LOAD

# ===========================
# 执行迁移
# ===========================
pgloader migration.load 2>&1 | tee pgloader_output.log

# ===========================
# 查看迁移报告
# ===========================
tail -50 pgloader_output.log
# 应包含: Total import time, Rows imported, Errors count
```

---

## 8. 数据转换规则与映射

### 8.1 数据类型映射表

| SQLite 类型 | Django Field | PostgreSQL 类型 | 转换规则 | 备注 |
|------------|-------------|----------------|---------|------|
| `INTEGER` | `AutoField` | `BIGSERIAL` | 自动递增 | 主键 |
| `INTEGER` | `IntegerField` | `INTEGER` | 直接映射 | - |
| `INTEGER` | `BigIntegerField` | `BIGINT` | 直接映射 | - |
| `INTEGER` | `SmallIntegerField` | `SMALLINT` | 直接映射 | - |
| `INTEGER` | `PositiveIntegerField` | `INTEGER` | CHECK 约束 | `>= 0` |
| `REAL` | `FloatField` | `DOUBLE PRECISION` | 精度提升 | PG 默认更高精度 |
| `TEXT` | `CharField` | `VARCHAR(n)` | 保留 max_length | 添加长度限制 |
| `TEXT` | `TextField` | `TEXT` | 直接映射 | 使用 TOAST 压缩 |
| `TEXT` | `EmailField` | `VARCHAR(254)` | 添加验证 | Django 层验证 |
| `BLOB` | `BinaryField` | `BYTEA` | 二进制存储 | Fernet 加密字段 |
| `NUMERIC` | `DecimalField` | `NUMERIC(p,s)` | 精度控制 | 指定 max_digits |
| `BOOLEAN` | `BooleanField` | `BOOLEAN` | 直接映射 | - |
| `DATE` | `DateField` | `DATE` | 直接映射 | - |
| `DATETIME` | `DateTimeField` | `TIMESTAMP WITH TIME ZONE` | 时区感知 | **重要!** |
| `TIME` | `TimeField` | `TIME` | 直接映射 | - |
| `JSON` | `JSONField` | **JSONB** | **二进制 JSON** | **性能大幅提升!** |
| - | `EncryptedCharField` | `BYTEA` | AES 加密后存储 | Fernet 库处理 |
| - | `EncryptedTextField` | `BYTEA` | AES 加密后存储 | Fernet 库处理 |
| - | `GenericIPAddressField` | `INET` | IP 地址类型 | **原生支持!** |
| - | `FileField` | `VARCHAR(100)` | 路径字符串 | 文件仍存文件系统 |
| - | `UUIDField` | `UUID` | UUID 类型 | **原生支持!** |

### 8.2 特殊字段处理详解

#### 8.2.1 加密字段 (Fernet Fields)

**当前实现** ([cmdb/models.py](file:///d:\codes\aiops\cmdb\models.py)):
```python
from fernet_fields import EncryptedCharField

class Server(models.Model):
    password = EncryptedCharField("SSH密码", max_length=100)
```

**迁移注意事项**:
- ✅ **好消息**: `django_fernet_fields_v2` 库同时支持 SQLite 和 PostgreSQL
- ✅ **无缝迁移**: 加密/解密逻辑在 Python 层，不依赖数据库特性
- ✅ **存储格式**: 在 PG 中同样存储为 BYTEA (二进制)

**验证步骤**:
```python
# 迁移后立即验证加密数据可解密
from cmdb.models import Server
server = Server.objects.first()
print(server.password)  # 应能正常解密显示明文
```

#### 8.2.2 JSONField 升级到 JSONB

**当前**: Django 的 JSONField 在 SQLite 中存储为 TEXT
**目标**: PostgreSQL 中升级为 JSONB (二进制 JSON，性能提升 10x+)

**优势对比**:
```sql
-- SQLite (TEXT 存储)
-- 查询: 需要全表扫描 + Python 解析
SELECT * FROM script_manager_taskexecution 
WHERE params->>'port' = '8080';  -- 慢!

-- PostgreSQL (JSONB 存储)
-- 查询: 使用 GIN 索引，毫秒级响应
CREATE INDEX idx_task_params ON script_manager_taskexecution USING gin (params);
SELECT * FROM script_manager_taskexecution 
WHERE params @> '{"port": "8080"}';  -- 快!
```

**自动转换**: Django ORM 会自动处理此转换，无需手动干预。

#### 8.2.3 DateTime 时区处理

**关键差异**:
- SQLite: 存储为 TEXT (ISO 8601 格式)，无时区概念
- PostgreSQL: 强烈建议使用 `TIMESTAMP WITH TIME ZONE`

**Django 配置** ([settings.py](file:///d:\codes\aiops\ops_platform/settings.py)):
```python
USE_TZ = True  # 已开启 ✅
TIME_ZONE = 'Asia/Shanghai'  # 已配置 ✅
```

**影响**:
- 所有 DateTimeField 将自动转换为 UTC 存储到 PG
- 显示时会自动转换为 Asia/Shanghai
- **无需手动调整**

#### 8.2.4 FileField 路径处理

**当前**: `TerminalLog.log_file` 存储相对路径 `ssh_logs/2025/12/09/audit_xxx.jsonl`
**迁移后**: 路径不变，但需确保文件系统可访问

**验证清单**:
```bash
# 确认文件存在
ls -la ssh_logs/2025/12/*/audit_*.jsonl | wc -l
# 应与数据库 TerminalLog 记录数匹配

# 检查 Django MEDIA_ROOT 配置
grep -r "MEDIA_ROOT" ops_platform/settings.py
# 确保 MEDIA_ROOT 指向正确的 ssh_logs 目录
```

#### 8.2.5 GenericIPAddressField → INET 类型

**优势**:
- PostgreSQL 原生 IP 地址类型
- 支持高效的范围查询和网络计算
- 自动验证 IP 格式合法性

**示例**:
```sql
-- 查找特定网段的服务器
SELECT * FROM cmdb_server 
WHERE ip_address <<= '192.168.1.0/24';  -- CIDR 范围查询!
```

### 8.3 数据清洗规则

#### 8.3.1 NULL 值处理

```python
# SQLite 允许一些不一致的 NULL 处理
# PostgreSQL 更严格，需要预先清理

# 示例: 清理空字符串转为 NULL
from django.db.models import F, Value
from django.db.models.functions import Coalesce

# 迁移前在 SQLite 上执行
Server.objects.filter(username='').update(username=None)
CloudAccount.objects.filter(region='').update(region=None)
```

#### 8.3.2 字符集统一

```bash
# 确保所有数据都是 UTF-8 编码
python << 'PYEOF'
import sqlite3

conn = sqlite3.connect('db.sqlite3')
cursor = conn.cursor()

# 检测非 UTF-8 字符
cursor.execute("""
    SELECT name FROM sqlite_master 
    WHERE type='table'
""")

tables = cursor.fetchall()
for (table_name,) in tables:
    try:
        cursor.execute(f"SELECT * FROM \"{table_name}\" LIMIT 1000")
        rows = cursor.fetchall()
        for row in rows:
            for value in row:
                if isinstance(value, str):
                    value.encode('utf-8')  # 尝试编码
    except UnicodeEncodeError as e:
        print(f"⚠️ 发现非 UTF-8 数据: {table_name} - {e}")

print("✅ 字符集检查完成")
conn.close()
PYEOF
```

#### 8.3.3 外键完整性修复

```bash
# 检查孤立记录 (引用了不存在的外键)
python << 'PYEOF'
import sqlite3

conn = sqlite3.connect('db.sqlite3')
cursor = conn.cursor()

# 示例: 检查 TerminalLog 是否有孤立的 server_id
cursor.execute("""
    SELECT COUNT(*) FROM cmdb_terminallog t
    LEFT JOIN cmdb_server s ON t.server_id = s.id
    WHERE s.id IS NULL AND t.server_id IS NOT NULL
""")
orphan_count = cursor.fetchone()[0]

if orphan_count > 0:
    print(f"⚠️ 发现 {orphan_count} 条孤立的 TerminalLog 记录")
    print("建议: 清理这些记录或设置有效的外键值")
else:
    print("✅ 外键完整性检查通过")

conn.close()
PYEOF
```

### 8.4 数据转换脚本 (可选增强)

```python
# scripts/pre_migration_cleanup.py
"""
迁移前数据清洗脚本
在执行正式迁移前运行此脚本
"""

import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ops_platform.settings')
django.setup()


def clean_empty_strings():
    """将空字符串转换为 None (NULL)"""
    from cmdb.models import Server, CloudAccount
    from k8s_manager.models import K8sCluster
    
    models_to_clean = [
        (Server, ['username', 'hostname', 'os_name']),
        (CloudAccount, ['name', 'region']),
        (K8sCluster, ['name', 'version']),
    ]
    
    total_fixed = 0
    for model, fields in models_to_clean:
        for field in fields:
            count = model.objects.filter(**{field: ''}).update(**{field: None})
            if count > 0:
                print(f"  ✓ {model.__name__}.{field}: 清理 {count} 条空字符串")
                total_fixed += count
    
    return total_fixed


def fix_orphan_records():
    """修复或删除孤儿记录"""
    from cmdb.models import TerminalLog, HighRiskAudit
    from django.db import connection
    
    orphan_actions = []
    
    # 方案 1: 将孤立记录的 server_id 设为 NULL
    with connection.cursor() as cursor:
        cursor.execute("""
            UPDATE cmdb_terminallog 
            SET server_id = NULL 
            WHERE server_id IS NOT NULL 
            AND server_id NOT IN (SELECT id FROM cmdb_server)
        """)
        fixed = cursor.rowcount
        if fixed > 0:
            orphan_actions.append(f"TerminalLog: {fixed} 条记录 server_id 设为 NULL")
    
    return orphan_actions


def validate_encrypted_data():
    """验证加密数据可正常解密"""
    from cmdb.models import Server, CloudAccount
    from ai_ops.models import AIModel
    
    errors = []
    
    # 测试 Server.password 解密
    for server in Server.objects.filter(password__isnull=False)[:10]:
        try:
            _ = server.password  # 触发解密
        except Exception as e:
            errors.append(f"Server id={server.id}: 解密失败 - {e}")
    
    # 测试 CloudAccount.secret_key 解密
    for account in CloudAccount.objects.all()[:5]:
        try:
            _ = account.secret_key
        except Exception as e:
            errors.append(f"CloudAccount id={account.id}: 解密失败 - {e}")
    
    # 测试 AIModel.api_key 解密
    for model in AIModel.objects.all()[:5]:
        try:
            _ = model.api_key
        except Exception as e:
            errors.append(f"AIModel id={model.id}: 解密失败 - {e}")
    
    return errors


def main():
    print("=" * 60)
    print("🔄 AiOPS 数据库迁移前数据清洗")
    print("=" * 60)
    
    print("\n[1/3] 清理空字符串...")
    cleaned = clean_empty_strings()
    print(f"  共清理 {cleaned} 条记录\n")
    
    print("[2/3] 修复孤儿记录...")
    orphans = fix_orphan_records()
    if orphans:
        for action in orphans:
            print(f"  ⚠️ {action}")
    else:
        print("  ✅ 未发现孤儿记录\n")
    
    print("[3/3] 验证加密数据...")
    enc_errors = validate_encrypted_data()
    if enc_errors:
        print("  ❌ 发现加密数据错误:")
        for err in enc_errors:
            print(f"    - {err}")
        return False
    else:
        print("  ✅ 所有加密数据验证通过\n")
    
    print("=" * 60)
    print("✅ 数据清洗完成! 可以开始正式迁移")
    print("=" * 60)
    return True


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
```

---

## 9. PgVector 扩展配置

### 9.1 扩展安装验证

```sql
-- ====================================
-- 以 Superuser 身份连接
-- ====================================
psql -U postgres -d aiops_db

-- ====================================
-- 1. 安装 PgVector 扩展
-- ====================================
CREATE EXTENSION IF NOT EXISTS vector;

-- 验证安装
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
-- 预期输出: vector | 0.7.4

-- 查看可用函数
\df vector.*
-- 应列出: vector, vector_in, vector_out, cosine_distance, l2_distance 等

-- ====================================
-- 2. 安装辅助扩展
-- ====================================
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- 三元组全文检索
CREATE EXTENSION IF NOT EXISTS btree_gin;  -- B-tree GIN 索引

-- ====================================
-- 3. 验证向量操作符
-- ====================================
-- 测试向量创建
SELECT '[1,2,3]'::vector;
-- 预期输出: [1, 2, 3]

-- 测试距离计算
SELECT cosine_distance('[1,2,3]'::vector, '[1,2,4]'::vector);
-- 预期输出: 一个小的浮点数

-- 测试内积
SELECT '[1,2,3]'::vector <#> '[4,5,6]'::vector;
-- 预期输出: 32 (内积结果)
```

### 9.2 为现有表添加向量列 (预留)

```sql
-- ====================================
-- 场景 1: AI 对话消息向量嵌入
-- 用于未来 RAG 知识库检索
-- ====================================

-- 添加向量列 (OpenAI text-embedding-3-small 维度为 1536)
ALTER TABLE ai_ops_chatmessage 
ADD COLUMN IF NOT EXISTS embedding VECTOR(1536);

-- 添加注释
COMMENT ON COLUMN ai_ops_chatmessage.embedding IS 'OpenAI text-embedding-3-small 向量嵌入 (1536维)';

-- ====================================
-- 场景 2: 运维知识库 (新建表)
-- ====================================
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

-- 创建注释
COMMENT ON TABLE ai_ops_knowledgebase IS 'AI 运维知识库 (RAG)';
COMMENT ON COLUMN ai_ops_knowledgebase.embedding IS '文档向量嵌入，用于语义搜索';

-- ====================================
-- 场景 3: 故障诊断案例库
-- ====================================
CREATE TABLE IF NOT EXISTS aiops_incident_cases (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    symptoms TEXT,           -- 故障现象描述
    root_cause TEXT,         -- 根因分析
    solution TEXT,           -- 解决方案
    severity VARCHAR(20),    -- 严重程度: critical/major/minor
    symptoms_vec VECTOR(768),  -- 使用较小维度节省空间
    solution_vec VECTOR(768),
    tags TEXT[],             -- PostgreSQL 数组类型!
    created_by INTEGER REFERENCES system_user(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    is_verified BOOLEAN DEFAULT FALSE  -- 是否经专家验证
);

COMMENT ON TABLE aiops_incident_cases IS '故障诊断案例库 (AI 学习素材)';
```

### 9.3 向量索引创建策略

```sql
-- ====================================
-- 索引算法选择指南
-- ====================================

/*
IVFFlat (Inverted File Flat):
  - 优点: 占用内存少，构建速度快
  - 缺点: 召回率略低，需要指定 lists 参数
  - 适用: 数据量 < 100万，内存受限

HNSW (Hierarchical Navigable Small World):
  - 优点: 召回率高，查询速度快
  - 缺点: 占用内存大，构建速度慢
  - 适用: 数据量 > 100万，追求高质量结果
*/

-- ====================================
-- 1. IVFFlat 索引 (适用于中小规模)
-- ====================================
-- 先插入一定量的数据再建索引效果更好
-- lists 参数: 建议 sqrt(行数)，例如 10万行 -> lists=316

CREATE INDEX idx_kb_embedding_ivfflat 
ON ai_ops_knowledgebase 
USING ivfflat (embedding vector_cosine_ops) 
WITH (lists = 100);

-- ====================================
-- 2. HNSW 索引 (适用于大规模，推荐)
-- ====================================
-- m: 每个节点的连接数 (默认 16，越大越精确但越慢)
-- ef_construction: 构建时搜索范围 (默认 64，越大越好但构建越慢)

CREATE INDEX idx_kb_embedding_hnsw 
ON ai_ops_knowledgebase 
USING hnsw (embedding vector_cosine_ops) 
WITH (m = 16, ef_construction = 64);

-- ====================================
-- 3. ChatMessage 向量索引
-- ====================================
CREATE INDEX idx_chatmsg_embedding 
ON ai_ops_chatmessage 
USING hnsw (embedding vector_cosine_ops) 
WITH (m = 16, ef_construction = 64);

-- ====================================
-- 4. 案例库双列索引
-- ====================================
CREATE INDEX idx_incident_symptoms 
ON aiops_incident_cases 
USING hnsw (symptoms_vec vector_cosine_ops);

CREATE INDEX idx_incident_solution 
ON ai_ops_incident_cases 
USING hnsw (solution_vec vector_cosine_ops);

-- ====================================
-- 验证索引
-- ====================================
\di+ *embedding*
\di+ *hnsw*
-- 应列出刚创建的索引及其大小
```

### 9.4 Django 模型集成 (未来使用)

```python
# ai_ops/models_pgvector.py (未来扩展)
"""
PgVector 集成模型示例
当需要启用 AI 知识库功能时，取消注释并执行 migrate
"""

from django.db import models
from pgvector.django import VectorField
from pgvector.django import HnswIndex, IvfflatIndex
from pgvector.django import CosineDistance, L2Distance


class KnowledgeBase(models.Model):
    """AI 运维知识库"""
    CATEGORY_CHOICES = [
        ('troubleshooting', '故障排查'),
        ('best_practice', '最佳实践'),
        ('security', '安全加固'),
        ('performance', '性能优化'),
        ('automation', '自动化'),
    ]
    
    title = models.CharField('标题', max_length=200)
    content = models.TextField('内容')
    category = models.CharField(
        '分类', 
        max_length=20, 
        choices=CATEGORY_CHOICES, 
        default='troubleshooting'
    )
    
    # PgVector 向量字段
    embedding = VectorField(
        dimensions=1536,  # OpenAI text-embedding-3-small
        null=True,
        blank=True
    )
    
    source_url = models.URLField('来源链接', blank=True, null=True)
    view_count = models.PositiveIntegerField('浏览次数', default=0)
    is_published = models.BooleanField('已发布', default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
        indexes = [
            HnswIndex(
                name='kb_embedding_idx',
                fields=['embedding'],
                opclasses=['vector_cosine_ops'],
                options={'m': 16, 'ef_construction': 64}
            )
        ]
    
    def __str__(self):
        return self.title
    
    def search_similar(self, query_embedding, limit=5):
        """语义搜索相似文档"""
        similar = KnowledgeBase.objects.annotate(
            similarity=CosineDistance('embedding', query_embedding)
        ).filter(
            embedding__isnull=False
        ).order_by('similarity')[:limit]
        
        return similar


class IncidentCase(models.Model):
    """故障诊断案例库"""
    SEVERITY_CHOICES = [
        ('critical', '紧急'),
        ('major', '重大'),
        ('minor', '一般'),
    ]
    
    title = models.CharField('标题', max_length=200)
    symptoms = models.TextField('故障现象')
    root_cause = models.TextField('根因分析')
    solution = models.TextField('解决方案')
    severity = models.CharField(
        '严重程度', 
        max_length=10, 
        choices=SEVERITY_CHOICES
    )
    
    # 双向量: 症状描述 + 解决方案
    symptoms_embedding = VectorField(dimensions=768, null=True, blank=True)
    solution_embedding = VectorField(dimensions=768, null=True, blank=True)
    
    tags = ArrayField(base_field=models.CharField(max_length=50), blank=True, default=list)
    created_by = models.ForeignKey('system.User', on_delete=models.SET_NULL, null=True)
    is_verified = models.BooleanField('专家验证', default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title
```

---

## 10. 详细迁移步骤分解

### 10.1 迁移前最终检查清单

```bash
# ===========================
# 迁移前 Checklist (逐项确认!)
# ===========================

echo "=== AiOps 数据库迁移前置检查 ==="
echo ""

# [ ] 1. 备份完成
test -f backups/pre_migration_*/db.sqlite3.backup && echo "✅ SQLite 备份存在" || echo "❌ 缺少 SQLite 备份"
test -f backups/pre_migration_*/django_full_export.json && echo "✅ Django JSON 导出存在" || echo "❌ 缺少 JSON 导出"

# [ ] 2. PostgreSQL 运行正常
pg_isready -h localhost -p 5432 && echo "✅ PostgreSQL 服务运行中" || echo "❌ PostgreSQL 未运行"

# [ ] 3. 数据库连接测试
psql -h localhost -U aiops_user -d aiops_db -c "SELECT 1;" > /dev/null 2>&1 && echo "✅ 数据库可连接" || echo "❌ 数据库连接失败"

# [ ] 4. 扩展已安装
psql -h localhost -U aiops_user -d aiops_db -c "SELECT extname FROM pg_extension WHERE extname='vector';" | grep -q vector && echo "✅ PgVector 已安装" || echo "❌ PgVector 未安装"

# [ ] 5. Python 环境就绪
python -c "import psycopg2; import django;" 2>/dev/null && echo "✅ Python 依赖完整" || echo "❌ Python 依赖缺失"

# [ ] 6. 应用服务停止 (可选，建议停机迁移)
# pgrep -f "daphne|celery" > /dev/null && echo "⚠️ 应用仍在运行 (建议停止)" || echo "✅ 应用已停止"

# [ ] 7. 磁盘空间充足
FREE_SPACE=$(df -BG /data/postgresql | awk 'NR==2{print $4}' | tr -d 'G')
[ "$FREE_SPACE" -gt 10 ] && echo "✅ 磁盘空间充足 (${FREE_SPACE}GB)" || echo "❌ 磁盘空间不足 (<10GB)"

echo ""
echo "=== 检查完成 ==="
# 如果所有项都通过，继续迁移；否则先解决问题
```

### 10.2 正式迁移步骤

#### **Step 0: 停止应用服务** (推荐，避免数据不一致)

```bash
# ===========================
# 停止 Django/Daphne 服务
# ===========================
# 如果使用 systemd
sudo systemctl stop aiops-daphne
sudo systemctl stop aiops-celery-worker
sudo systemctl stop aiops-celery-beat

# 如果使用 Docker Compose
docker-compose down

# 如果直接进程启动
pkill -f "daphne ops_platform.asgi"
pkill -f "celery.*ops_platform"

# 验证所有进程已停止
pgrep -af "(daphne|celery)" || echo "✅ 所有应用进程已停止"
```

#### **Step 1: 执行数据清洗脚本**

```bash
cd d:\codes\aiops
source venv/bin/activate

# 运行清洗脚本 (第8章定义的 pre_migration_cleanup.py)
python scripts/pre_migration_cleanup.py

# 预期输出:
# ✅ 数据清洗完成! 可以开始正式迁移
```

#### **Step 2: 修改 Django 配置指向 PostgreSQL**

```python
# ops_platform/settings.py - 修改 DATABASES 配置

import os

DATABASES = {
    'default': {
        # ======== 修改开始 ========
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'aiops_db'),
        'USER': os.environ.get('DB_USER', 'aiops_user'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'YourStrongPasswordHere!'),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        # ======== 修改结束 ========
        
        'OPTIONS': {
            'options': '-c statement_timeout=30000',  # 30秒查询超时
        },
        
        # 连接池配置 (生产环境重要!)
        'CONN_MAX_AGE': 60,  # 连接复用时间(秒)，0表示每次新建
        'CONN_HEALTH_CHECKS': True,  # Django 4.1+ 健康检查
    }
}

# 可选: 添加 PostgreSQL 特定优化
if DATABASES['default']['ENGINE'] == 'django.db.backends.postgresql':
    DATABASES['default']['OPTIONS']['options'] += ' -c lock_timeout=5000'  # 锁等待超时
```

#### **Step 3: 创建数据库表结构 (空表)**

```bash
cd d:\codes\aiops
source venv/bin/activate

# 设置环境变量
export DB_NAME=aiops_db
export DB_USER=aiops_user
export DB_PASSWORD='YourStrongPasswordHere!'
export DB_HOST=localhost
export DB_PORT=5432

# 执行 migrate 创建表结构
python manage.py migrate --run-syncdb 2>&1 | tee migrate_output.log

# 验证表创建成功
echo ""
echo "=== 验证表结构 ==="
python manage.py dbshell << 'SQL'
-- 列出所有业务表
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;

-- 统计表数量
SELECT count(*) as total_tables 
FROM information_schema.tables 
WHERE table_schema = 'public';
SQL

# 预期输出: ~35 张表 (与 SQLite 一致)
```

**预期输出示例**:
```
Operations to perform:
  Apply all migrations: system, cmdb, k8s_manager, script_manager, ai_ops, contenttypes, auth, sessions, admin
Running migrations:
  Applying contenttypes.0001_initial... OK
  Applying auth.0001_initial... OK
  Applying system.0001_initial... OK
  ...
  Applying k8s_manager.0001_initial... OK
  Applying ai_ops.0002_initial... OK
```

#### **Step 4: 从 SQLite 导出数据 (JSON 格式)**

```bash
# ===== 重要: 此步骤需要临时切回 SQLite 配置! =====

# 方法 A: 使用环境变量切换 (推荐)
export DJANGO_SETTINGS_MODULE=ops_platform.settings_sqlite  # 临时配置文件

# 或者方法 B: 直接修改 settings.py 指回 SQLite (记得备份后再改!)

# 导出数据 (使用 natural foreign key 保持关系完整性)
python manage.py dumpdata \
  --natural-foreign \
  --natural-primary \
  --indent 2 \
  system \
  cmdb \
  k8s_manager \
  script_manager \
  ai_ops \
  auth \
  contenttypes \
  admin \
  sessions \
  > data_export.json

# 压缩导出文件
gzip data_export.json

# 查看文件大小
ls -lh data_export.json.gz
# 预期: 取决于数据量，通常 50MB - 500MB

echo "✅ 数据导出完成"
```

**创建临时 SQLite 配置文件** (`settings_sqlite.py`):
```python
# settings_sqlite.py - 仅用于数据导出
from .settings import *

# 覆盖数据库配置为 SQLite
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
```

#### **Step 5: 导入数据到 PostgreSQL**

```bash
# ===== 切回 PostgreSQL 配置 =====
unset DJANGO_SETTINGS_MODULE  # 或设置为默认 settings

# 分批导入 (大数据量时更稳定)
python manage.py loaddata data_export.json 2>&1 | tee loaddata_output.log

# 监控进度
# Django loaddata 会显示每个模型的导入数量

# 预期输出示例:
# Installed 5 object(s) from 1 fixture(s)  (auth.Permission)
# Installed 3 object(s) from 1 fixture(s)  (auth.Group)
# Installed 12 object(s) from 1 fixture(s) (system.User)
# Installed 150 object(s) from 1 fixture(s) (cmdb.Server)
# ...

# 如果遇到内存不足错误，分批导入:
# python manage.py loaddata system.json
# python manage.py loaddata cmdb.json
# python manage.py loaddata k8s_manager.json
# python manage.py loaddata script_manager.json
# python manage.py loaddata ai_ops.json
# python manage.py loaddata auth.json contenttypes.json sessions.json admin.json
```

#### **Step 6: 更新序列值 (Sequence Reset)**

```bash
# PostgreSQL 的自增主键需要同步序列值
python manage.py sqlsequencereset | python manage.py dbshell

# 或者手动执行
python manage.py shell << 'PYEOF'
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT setval(
            pg_get_serial_sequence('"table_name"', 'id'),
            COALESCE(MAX(id), 1)
        ) FROM "table_name";
    """)
    # 对每张有自增主键的表执行上述操作
print("✅ 序列值已更新")
PYEOF
```

#### **Step 7: 验证初始数据完整性**

```bash
python << 'PYEOF'
import os
import sys
import django

sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ops_platform.settings')
django.setup()

print("=== 数据完整性快速验证 ===\n")

from django.db import connection
from django.apps import apps

tables_to_check = [
    ('system', 'User'),
    ('cmdb', 'Server'),
    ('cmdb', 'ServerMetric'),
    ('cmdb', 'TerminalLog'),
    ('k8s_manager', 'K8sCluster'),
    ('script_manager', 'Script'),
    ('ai_ops', 'AIModel'),
]

for app_label, model_name in tables_to_check:
    try:
        Model = apps.get_model(app_label, model_name)
        count = Model.objects.count()
        print(f"  ✓ {app_label}.{model_name}: {count} 条记录")
    except Exception as e:
        print(f"  ✗ {app_label}.{model_name}: 错误 - {e}")

print("\n✅ 快速验证完成")
PYEOF
```

---

## 11. Django 配置修改指南

### 11.1 完整的 settings.py 修改对比

```python
# ====================================
# 文件: ops_platform/settings.py
# 位置: 第 130-170 行附近 (DATABASES 部分)
# ====================================

# ========== 修改前 (SQLite) ==========
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# ========== 修改后 (PostgreSQL) ==========
import os

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'aiops_db'),
        'USER': os.environ.get('DB_USER', 'aiops_user'),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        
        # PostgreSQL 优化选项
        'OPTIONS': {
            'options': '-c statement_timeout=30000'  # 30秒超时
        },
        
        # 连接池 (Django 4.1+)
        'CONN_MAX_AGE': 60,           # 连接复用 60 秒
        'CONN_HEALTH_CHECKS': True,   # 启用健康检查
        'TIME_ZONE': 'Asia/Shanghai', # 时区设置
    }
}
```

### 11.2 新增 PostgreSQL 专用配置

```python
# 在 settings.py 末尾添加 (或创建 settings_postgres.py)

# ====================================
# PostgreSQL 数据库优化配置
# ====================================

# 如果是 PostgreSQL，启用额外优化
if DATABASES['default']['ENGINE'] == 'django.db.backends.postgresql':
    
    # 1. 数据库连接池 (使用 django-db-geventpool 或 pgbouncer)
    DATABASES['default']['OPTIONS']['options'] += ' -c pool_size=20'
    
    # 2. 全文搜索配置 (用于日志检索)
    POSTGRES_SEARCH_CONFIG = 'simple'  # 或 'chinese_groovy' (中文)
    
    # 3. PgVector 配置 (预留)
    PGVECTOR_DIMENSIONS = 1536  # OpenAI embedding 维度
    
    # 4. 批量操作优化
    BATCH_SIZE = 1000  # bulk_create 默认批次大小
```

### 11.3 requirements.txt 更新

```txt
# 在现有依赖基础上新增:

# PostgreSQL 数据库适配器 (二选一)
psycopg2-binary==2.9.9          # 推荐: 开箱即用，无需编译
# psycopg[binary]==3.1.19       # 替代方案: 现代 async 支持

# PgVector Django 集成 (未来启用 AI 功能时安装)
# pgvector==0.2.4                # Django ORM 集成
# 注意: 先安装 C 扩展库 libpq-dev

# 性能监控 (可选)
# django-debug-toolbar==4.2.0   # 开发环境 SQL 调试
# django-silk==5.1.0            # 生产环境性能分析
```

### 11.4 Docker Compose 配置示例

```yaml
# docker-compose.yml (PostgreSQL 版本)
version: '3.8'

services:
  web:
    build: .
    command: daphne -b 0.0.0.0 -p 8000 ops_platform.asgi:application
    volumes:
      - .:/app
      - ssh_logs_data:/app/ssh_logs  # 持久化 SSH 日志
    environment:
      - DJANGO_DEBUG=False
      - DB_NAME=aiops_db
      - DB_USER=aiops_user
      - DB_PASSWORD=${POSTGRES_PASSWORD}
      - DB_HOST=db
      - DB_PORT=5432
      - REDIS_HOST=redis
    ports:
      - "8000:8000"
    depends_on:
      - db
      - redis
    restart: unless-stopped

  db:
    image: postgres:18-alpine
    environment:
      POSTGRES_DB: aiops_db
      POSTGRES_USER: aiops_user
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./postgres/init.sql:/docker-entrypoint-initdb.d/init.sql  # 初始化脚本
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U aiops_user -d aiops_db"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    restart: unless-stopped

  celery_worker:
    build: .
    command: celery -A ops_platform worker -l info -P eventlet -c 4
    volumes:
      - .:/app
    environment:
      - DB_NAME=aiops_db
      - DB_USER=aiops_user
      - DB_PASSWORD=${POSTGRES_PASSWORD}
      - DB_HOST=db
      - REDIS_HOST=redis
    depends_on:
      - db
      - redis
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
  ssh_logs_data:

# .env 文件 (不要提交到 Git!)
POSTGRES_PASSWORD=YourStrongPasswordHere!
REDIS_PASSWORD=123456
```

---

## 12. 数据验证方法

### 12.1 自动化验证脚本

```python
# scripts/post_migration_validation.py
"""
迁移后数据验证脚本
验证数据完整性、一致性、功能可用性
"""

import os
import sys
import json
import django
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ops_platform.settings')
django.setup()


class MigrationValidator:
    """迁移验证器"""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.passed = 0
        
    def log(self, status, message):
        icon = {'PASS': '✅', 'FAIL': '❌', 'WARN': '⚠️'}[status]
        print(f"  {icon} {message}")
        if status == 'FAIL':
            self.errors.append(message)
        elif status == 'WARN':
            self.warnings.append(message)
        else:
            self.passed += 1
    
    def validate_table_counts(self):
        """验证各表记录数"""
        print("\n[1/6] 验证表记录数...")
        
        expected_counts = {
            'system.User': None,  # 动态获取
            'cmdb.Server': None,
            'cmdb.ServerMetric': None,
            'cmdb.TerminalLog': None,
            'k8s_manager.K8sCluster': None,
            'script_manager.Script': None,
            'ai_ops.AIModel': None,
            'ai_ops.ChatSession': None,
            'ai_ops.ChatMessage': None,
        }
        
        from django.apps import apps
        
        for model_path in expected_counts.keys():
            app_label, model_name = model_path.split('.')
            try:
                Model = apps.get_model(app_label, model_name)
                count = Model.objects.count()
                expected_counts[model_path] = count
                self.log('PASS', f"{model_path}: {count} 条记录")
            except Exception as e:
                self.log('FAIL', f"{model_path}: 无法查询 - {e}")
        
        return expected_counts
    
    def validate_foreign_keys(self):
        """验证外键引用完整性"""
        print("\n[2/6] 验证外键完整性...")
        
        from django.db import connection
        
        checks = [
            ("cmdb_terminallog", "server_id", "cmdb_server", "id"),
            ("cmdb_highriskaudit", "server_id", "cmdb_server", "id"),
            ("cmdb_servermetric", "server_id", "cmdb_server", "id"),
            ("ai_ops_chatsession", "user_id", "system_user", "id"),
            ("script_manager_tasklog", "server_id", "cmdb_server", "id"),
        ]
        
        for table, fk_col, ref_table, ref_col in checks:
            with connection.cursor() as cursor:
                cursor.execute(f"""
                    SELECT COUNT(*) FROM {table} 
                    WHERE {fk_col} IS NOT NULL 
                    AND {fk_col} NOT IN (SELECT {ref_col} FROM {ref_table})
                """)
                orphan_count = cursor.fetchone()[0]
                
                if orphan_count == 0:
                    self.log('PASS', f"{table}.{fk_col} → {ref_table}: 无孤儿记录")
                else:
                    self.log('WARN', f"{table}.{fk_col} → {ref_table}: 发现 {orphan_count} 条孤儿记录")
    
    def validate_encrypted_fields(self):
        """验证加密字段可解密"""
        print("\n[3/6] 验证加密字段...")
        
        from cmdb.models import Server, CloudAccount
        from ai_ops.models import AIModel
        from k8s_manager.models import K8sCluster
        
        tests = [
            ('Server.password', Server.objects.filter(password__isnull=False).first()),
            ('CloudAccount.secret_key', CloudAccount.objects.first()),
            ('AIModel.api_key', AIModel.objects.first()),
            ('K8sCluster.kubeconfig', K8sCluster.objects.first()),
        ]
        
        for field_name, instance in tests:
            if not instance:
                self.log('WARN', f"{field_name}: 无测试数据，跳过")
                continue
            
            try:
                # 触发解密
                _ = getattr(instance, field_name.split('.')[-1])
                self.log('PASS', f"{field_name}: 解密成功")
            except Exception as e:
                self.log('FAIL', f"{field_name}: 解密失败 - {e}")
    
    def validate_datetime_fields(self):
        """验证日期时间字段时区正确性"""
        print("\n[4/6] 验证日期时间字段...")
        
        from django.utils import timezone
        from cmdb.models import Server, TerminalLog
        from ai_ops.models import ChatMessage
        
        # 检查最新记录是否有合理的时区信息
        server = Server.objects.order_by('-created_at').first()
        if server and server.created_at:
            if timezone.is_aware(server.created_at):
                self.log('PASS', f"Server.created_at: 时区感知 ({server.created_at.tzinfo})")
            else:
                self.log('WARN', f"Server.created_at: 无时区信息 (naive datetime)")
        
        msg = ChatMessage.objects.order_by('-created_at').first()
        if msg and msg.created_at:
            if timezone.is_aware(msg.created_at):
                self.log('PASS', f"ChatMessage.created_at: 时区感知")
            else:
                self.log('WARN', f"ChatMessage.created_at: 无时区信息")
    
    def validate_json_fields(self):
        """验证 JSONField 升级为 JSONB"""
        print("\n[5/6] 验证 JSON 字段...")
        
        from script_manager.models import TaskExecution
        from django.db import connection
        
        # 检查 params 字段类型是否为 jsonb
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT data_type 
                FROM information_schema.columns 
                WHERE table_name = 'script_manager_taskexecution' 
                AND column_name = 'params'
            """)
            result = cursor.fetchone()
            
            if result and result[0].lower() == 'jsonb':
                self.log('PASS', "TaskExecution.params: 已升级为 JSONB ✨")
            elif result:
                self.log('WARN', f"TaskExecution.params: 类型为 {result[0]} (期望 jsonb)")
        
        # 测试 JSON 查询性能
        try:
            task = TaskExecution.objects.filter(params__isnull=False).first()
            if task and task.params:
                self.log('PASS', f"TaskExecution.params: 内容可访问, 类型={type(task.params)}")
        except Exception as e:
            self.log('FAIL', f"TaskExecution.params 查询失败 - {e}")
    
    def validate_special_types(self):
        """验证特殊数据类型 (INET, UUID 等)"""
        print("\n[6/6] 验证特殊数据类型...")
        
        from django.db import connection
        from cmdb.models import Server
        
        # 检查 IP 地址字段类型
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT data_type, udt_name 
                FROM information_schema.columns 
                WHERE table_name = 'cmdb_server' 
                AND column_name = 'ip_address'
            """)
            result = cursor.fetchone()
            
            if result and result[1] == 'inet':
                self.log('PASS', "Server.ip_address: INET 类型 ✨ (支持 CIDR 查询)")
            else:
                self.log('INFO', f"Server.ip_address: 当前类型 {result}")
        
        # 测试 IP 地址查询
        server = Server.objects.first()
        if server and server.ip_address:
            self.log('PASS', f"IP 地址示例: {server.ip_address}")
    
    def run_all(self):
        """执行所有验证"""
        print("=" * 70)
        print("🔍 AiOps 数据库迁移后验证")
        print(f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)
        
        self.validate_table_counts()
        self.validate_foreign_keys()
        self.validate_encrypted_fields()
        self.validate_datetime_fields()
        self.validate_json_fields()
        self.validate_special_types()
        
        print("\n" + "=" * 70)
        print(f"📊 验证结果汇总:")
        print(f"  ✅ 通过: {self.passed}")
        print(f"  ⚠️  警告: {len(self.warnings)}")
        print(f"  ❌ 失败: {len(self.errors)}")
        print("=" * 70)
        
        if self.errors:
            print("\n❌ 发现以下问题需要修复:")
            for err in self.errors:
                print(f"  • {err}")
            return False
        else:
            print("\n🎉 所有关键验证通过! 迁移成功!")
            return True


if __name__ == '__main__':
    validator = MigrationValidator()
    success = validator.run_all()
    sys.exit(0 if success else 1)
```

### 12.2 SQL 级别深度验证

```sql
-- ====================================
-- 在 psql 中执行的验证查询
-- ====================================
\connect aiops_db

-- 1. 统计所有表的行数
CREATE OR REPLACE VIEW v_table_stats AS
SELECT 
    schemaname,
    tablename,
    n_live_tup as row_count,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as total_size
FROM pg_stat_user_tables 
ORDER BY n_live_tup DESC;

SELECT * FROM v_table_stats;
-- 预期: 与 SQLite 中的记录数一致

-- 2. 检查外键约束状态
SELECT
    tc.table_name, 
    tc.constraint_name,
    tc.constraint_type,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name
FROM information_schema.table_constraints AS tc 
JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage AS ccu
    ON ccu.constraint_name = tc.constraint_name
WHERE constraint_type = 'FOREIGN KEY'
AND tc.table_schema = 'public';
-- 预期: 列出所有外键关系，无异常

-- 3. 检查索引状态
SELECT 
    indexname,
    indexdef,
    pg_size_pretty(pg_relation_size(indexname)) as index_size
FROM pg_indexes 
WHERE schemaname = 'public'
ORDER BY indexname;

-- 4. 检查序列值是否正确
SELECT 
    c.relname as sequence_name,
    last_value,
    max_value
FROM pg_sequences s
JOIN pg_class c ON c.oid = s.seqrelid
ORDER BY c.relname;

-- 5. 验证 PgVector 扩展
SELECT 
    extname, 
    extversion,
    nspname as schema
FROM pg_extension 
WHERE extname IN ('vector', 'pg_trgm', 'btree_gin');

-- 6. 查看表空间使用情况
SELECT 
    pg_size_pretty(pg_database_size('aiops_db')) as database_size,
    pg_size_pretty(pg_database_size('postgres')) as template_size;
```

### 12.3 功能级验证清单

```markdown
## 功能验证 CheckList

### 用户认证模块
- [ ] 用户登录 (admin / 普通用户)
- [ ] LDAP 认证 (如果配置了)
- [ ] 密码修改
- [ ] 会话保持 (Session)
- [ ] 权限控制 (RBAC)

### CMDB 资产管理
- [ ] 服务器列表展示
- [ ] 服务器详情查看
- [ ] 新增/编辑/删除服务器
- [ ] 服务器分组树形展示
- [ ] 云账号同步 (阿里云/腾讯云)

### WebSSH 终端
- [ ] WebSocket 连接建立
- [ ] SSH 登录成功
- [ ] 命令执行与回显
- [ ] 终端录像录制
- [ ] 高危命令拦截 (AI 审计)
- [ ] 文件上传/下载 (SFTP)

### 监控指标
- [ ] 实时 CPU/内存/磁盘图表
- [ ] 历史趋势图加载
- [ ] 指标数据写入 (Agent 上报)
- [ ] 告警阈值触发

### K8s 管理
- [ ] 集群列表展示
- [ ] Pod/Deployment/Service 列表
- [ ] YAML 编辑器加载
- [ ] Web Shell 进入容器
- [ ] 实时日志查看

### 脚本管理
- [ ] 脚本列表/编辑
- [ ] 任务创建与执行
- [ ] 执行日志实时显示
- [ ] 批量并发执行

### AI 功能
- [ ] AI 模型列表
- [ ] 服务器故障诊断
- [ ] SSH 审计分析
- [ ] AI 对话平台
- [ ] 消息历史查询

### SSL 证书
- [ ] 证书列表
- [ ] 过期检测
- [ ] 告警通知 (钉钉/企微)
```

---

## 13. 潜在风险评估及应对措施

### 13.1 风险矩阵总览

| 风险ID | 风险描述 | 概率 | 影响 | 风险等级 | 应对策略 |
|--------|---------|------|------|---------|---------|
| R01 | 数据丢失或不一致 | 低 | 极高 | 🔴 P0 | 多重备份 + 事务保证 |
| R02 | 迁移过程中断 | 中 | 高 | 🔴 P0 | 断点续传 + 回滚机制 |
| R03 | 加密数据无法解密 | 低 | 极高 | 🔴 P0 | 迁移前验证 + 密钥一致性 |
| R04 | 性能不达预期 | 中 | 中 | 🟠 P1 | 索引优化 + 查询调优 |
| R05 | 时区数据处理错误 | 中 | 高 | 🟠 P1 | USE_TZ 配置 + 数据校验 |
| R06 | Django 版本兼容问题 | 低 | 中 | 🟡 P2 | 依赖锁定 + 测试覆盖 |
| R07 | 连接池耗尽 | 中 | 中 | 🟡 P2 | PgBouncer + 连接复用 |
| R08 | 磁盘空间不足 | 低 | 高 | 🟠 P1 | 容量规划 + 监控告警 |
| R09 | 字符集乱码 | 低 | 中 | 🟡 P2 | UTF-8 强制 + 校验脚本 |
| R10 | 外键约束冲突 | 中 | 中 | 🟡 P2 | 数据清洗 + 孤儿处理 |

### 13.2 关键风险详细应对

#### **R01: 数据丢失风险**

**风险场景**: dumpdata/loaddata 过程中数据截断或编码错误

**预防措施**:
```bash
# 1. 三重备份策略
backup_1: SQLite 原始文件 (.sqlite3)
backup_2: SQL Dump (.dump.sql)
backup_3: Django JSON Export (.json)

# 2. 导出后立即验证 MD5
md5sum data_export.json > data_export.md5

# 3. 导入前后对比记录数
# 导出前
python manage.py shell -c "
from django.apps import apps; 
[print(f'{m.__name__}: {m.objects.count()}') 
 for m in [apps.get_model(a, b) for a,b in [('cmdb','Server'),('ai_ops','ChatMessage')]]"
> counts_before.txt

# 导入后对比
diff counts_before.txt counts_after.txt
```

**应急响应**:
```bash
# 如果发现数据丢失
# Step 1: 立即停止应用
# Step 2: 从备份恢复
dropdb aiops_db && createdb aiops_db
python manage.py migrate
python manage.py loaddata data_export.json
# Step 3: 重新验证
python scripts/post_migration_validation.py
```

#### **R02: 迁移中断风险**

**风险场景**: loaddata 过程中 OOM (内存不足) 或网络中断

**解决方案**: 分批导入 + 断点续传

```python
# scripts/batch_loaddata.py
"""分批导入工具，支持断点续传"""

import os
import sys
import json
import django

sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ops_platform.settings')
django.setup()

from django.core.management import call_command
from io import StringIO


def batch_import(json_file, batch_size=50000):
    """
    分批导入 JSON 数据
    支持从指定偏移量恢复 (断点续传)
    """
    progress_file = f"{json_file}.progress"
    start_offset = 0
    
    # 检查是否有进度文件 (断点续传)
    if os.path.exists(progress_file):
        with open(progress_file, 'r') as f:
            start_offset = int(f.read().strip())
        print(f"🔄 从第 {start_offset} 行恢复导入...")
    
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    total = len(data)
    print(f"📦 总计 {total} 条记录待导入")
    
    for i in range(start_offset, total, batch_size):
        batch = data[i:i+batch_size]
        batch_json = json.dumps(batch, indent=2, ensure_ascii=False)
        
        try:
            # 使用 StringIO 作为标准输入
            call_command('loaddata', '-', stdin=StringIO(batch_json))
            
            # 更新进度
            end_idx = min(i + batch_size, total)
            with open(progress_file, 'w') as pf:
                pf.write(str(end_idx))
            
            print(f"  ✅ 已导入 {end_idx}/{total} ({end_idx*100//total}%)")
            
        except Exception as e:
            print(f"  ❌ 导入失败于第 {i} 条: {e}")
            print(f"  💾 进度已保存，可重新运行此脚本恢复")
            return False
    
    # 完成，清理进度文件
    if os.path.exists(progress_file):
        os.remove(progress_file)
    
    print(f"\n🎉 全部导入完成!")
    return True


if __name__ == '__main__':
    json_file = sys.argv[1] if len(sys.argv) > 1 else 'data_export.json'
    success = batch_import(json_file)
    sys.exit(0 if success else 1)
```

#### **R03: 加密数据解密失败**

**根因分析**: Fernet 密钥 (`APP_MASTER_KEY`) 不一致

**预防措施**:
```bash
# 1. 迁移前记录当前使用的 Fernet Key
grep "APP_MASTER_KEY" .env.production
# 确保: 新旧环境使用相同的 APP_MASTER_KEY!

# 2. 导出前强制验证所有加密字段
python << 'PYEOF'
from cmdb.models import Server, CloudAccount
from ai_ops.models import AIModel
from k8s_manager.models import K8sCluster

tests = [
    ('Server', Server.objects.all(), 'password'),
    ('CloudAccount', CloudAccount.objects.all(), 'secret_key'),
    ('AIModel', AIModel.objects.all(), 'api_key'),
    ('K8sCluster', K8sCluster.objects.all(), 'kubeconfig'),
]

errors = []
for model_name, queryset, field in tests:
    for obj in queryset:
        try:
            getattr(obj, field)  # 尝试解密
        except Exception as e:
            errors.append(f"{model_name} id={obj.id}.{field}: {e}")

if errors:
    print("❌ 加密数据验证失败:")
    for err in errors[:10]:  # 只显示前10个
        print(f"  {err}")
    exit(1)
else:
    print("✅ 所有加密数据验证通过")
PYEOF
```

**应急方案**:
```bash
# 如果发现密钥不匹配:
# 1. 找到原始的 APP_MASTER_KEY (可能在旧的环境变量或 settings.py 备份中)
# 2. 设置正确的密钥后重新导入
# 3. 如果原始密钥丢失，这些加密数据将无法恢复!
#    必须让用户重新输入密码/API Key
```

#### **R05: 时区处理风险**

**问题**: SQLite 存储 naive datetime，PG 期望 aware datetime

**影响范围**: `created_at`, `updated_at`, `start_time`, `expire_date` 等所有 DateTimeField

**解决方案**:
```python
# Django 自动处理大部分情况，但需确保:
# 1. settings.py 中 USE_TZ = True (已配置 ✅)
# 2. 迁移后手动修复可能的 naive datetime

from django.utils import timezone
from django.db import connection

# 检测并修复 naive datetime
with connection.cursor() as cursor:
    cursor.execute("""
        UPDATE cmdb_server 
        SET created_at = created_at AT TIME ZONE 'Asia/Shanghai'
        WHERE created_at::text NOT LIKE '%+%'
        AND created_at IS NOT NULL
    """)
    fixed = cursor.rowcount
    if fixed > 0:
        print(f"⚠️  修复了 {fixed} 条 naive datetime 记录")
```

### 13.3 性能风险评估

#### **常见性能退化场景及优化**

```sql
-- ====================================
-- 场景 1: ServerMetric 表查询慢
-- 问题: 数据量大 (百万级)，缺少合适索引
-- 解决: 复合索引 + 分区表 (未来)
-- ====================================

-- 当前索引 (已有)
CREATE INDEX idx_servermetric_server_time 
ON cmdb_servermetric (server_id, created_at DESC);

-- 优化: 添加部分索引 (只索引最近30天)
CREATE INDEX idx_servermetric_recent 
ON cmdb_servermetric (server_id, created_at DESC)
WHERE created_at > NOW() - INTERVAL '30 days';

-- 场景 2: TerminalLog 全文搜索慢
-- 解决: Pg_Trigram GIN 索引
CREATE INDEX idx_terminallog_command_trgm 
ON cmdb_highriskaudit USING gin (command gin_trgm_ops);

-- 场景 3: ChatMessage 对话历史加载慢
-- 解决: 复合索引 + LIMIT 优化
CREATE INDEX idx_chatmessage_session_time 
ON ai_ops_chatmessage (session_id, created_at);

-- 场景 4: 多表 JOIN 慢 (Dashboard 查询)
-- 解决: 物化视图 (Materialized View)
CREATE MATERIALIZED VIEW mv_dashboard_stats AS
SELECT 
    (SELECT count(*) FROM cmdb_server) as total_servers,
    (SELECT count(*) FROM cmdb_server WHERE status='Running') as running_servers,
    (SELECT count(*) FROM k8s_manager_k8scluster) as total_clusters,
    (SELECT count(*) FROM ai_ops_chatsession) as total_sessions
WITH DATA;

-- 定期刷新物化视图 (通过 Celery Beat)
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_dashboard_stats;
```

---

## 14. 回滚方案

### 14.1 即时回滚 (Rollback Plan)

#### **场景 A: 迁移过程中发现问题**

```bash
# ===== 立即停止当前操作 =====
# Ctrl+C 中断 loaddata 进程

# ===== 回滚步骤 =====
# 1. 删除 PostgreSQL 中可能已经导入的不完整数据
psql -h localhost -U aiops_user -d aiops_db << 'SQL'
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO aiops_user;
GRANT ALL ON SCHEMA public TO PUBLIC;
SQL

# 2. 重建扩展
psql -h localhost -U aiops_user -d aiops_db << 'SQL'
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
SQL

# 3. 恢复 Django 配置指向 SQLite
# 编辑 settings.py 将 DATABASES 改回 SQLite

# 4. 验证 SQLite 数据完好
sqlite3 db.sqlite3 "SELECT count(*) FROM cmdb_server;"
# 应返回原有数量

# 5. 重启应用服务
sudo systemctl start aiops-daphne
sudo systemctl start aiops-celery-worker

echo "✅ 已回滚至 SQLite，系统恢复正常"
```

#### **场景 B: 迁移完成后发现严重问题**

```bash
# ===== 完整回滚流程 =====
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# 1. 备份当前的 PG 数据 (以防万一)
pg_dump -h localhost -U aiops_user -d aiops_db > backups/failed_pg_backup_$TIMESTAMP.sql

# 2. 停止所有应用服务
sudo systemctl stop aiops-daphne aiops-celery-worker aiops-celery-beat

# 3. 恢复 SQLite 数据库
cp backups/pre_migration_*/db.sqlite3.backup db.sqlite3
chmod 644 db.sqlite3

# 4. 恢复 SSH 日志文件 (如有变更)
rm -rf ssh_logs
cp -r backups/pre_migration_*/ssh_logs_backup ssh_logs

# 5. 修改配置回 SQLite
# 编辑 settings.py 或设置环境变量
export DB_ENGINE=django.db.backends.sqlite3

# 6. 验证 SQLite 数据
python manage.py check
python manage.py shell -c "from cmdb.models import Server; print(Server.objects.count())"

# 7. 重启服务
sudo systemctl start aiops-daphne aiops-celery-worker aiops-celery-beat

# 8. 功能验证
curl -s http://localhost:8000/login/ | grep -q "AiOps" && echo "✅ 系统已恢复"

echo "🔄 回滚完成，系统运行在 SQLite 上"
```

### 14.2 回滚决策树

```
发现问题时:
│
├─ 迁移过程中 (loaddata 进行中)?
│  ├─ 是 → Ctrl+C 停止 → 清理 PG → 回滚配置 → 重启服务
│  │       预计耗时: 5-10 分钟
│  │
│  └─ 否 (迁移已完成)?
│      ├─ 问题严重程度?
│      │  ├─ 致命 (数据丢失/无法登录)?
│      │  │  → 立即回滚 SQLite (<15分钟)
│      │  │
│      │  ├─ 严重 (核心功能不可用)?
│      │  │  → 评估修复时间
│      │  │  ├─ <30分钟可修复 → 尝试热修复
│      │  │  └─ >30分钟 → 回滚 SQLite
│      │  │
│      │  └─ 轻微 (非核心功能/性能问题)?
│      │     → 记录问题 → 计划下次迭代修复
│      │     → 继续观察
│      │
│      └─ 通知利益相关者
│         └─ 发送回滚/故障报告
```

### 14.3 回滚后行动项

```markdown
## 回滚后 Checklist

- [ ] 确认所有服务正常运行
- [ ] 验证核心功能 (登录、WebSSH、监控)
- [ ] 编写故障报告 (Root Cause Analysis)
- [ ] 分析失败原因
- [ ] 制定修正后的迁移计划
- [ ] 安排下次迁移窗口 (建议至少间隔24小时)
- [ ] 通知所有用户系统已恢复
- [ ] 更新运维文档和 Runbook
```

---

## 15. 系统测试计划

### 15.1 测试阶段划分

```
Phase 1: 单元测试 (Unit Tests)          [Day 4 上午]
  ↓
Phase 2: 集成测试 (Integration Tests)   [Day 4 下午]
  ↓
Phase 3: 性能测试 (Performance Tests)    [Day 5 上午]
  ↓
Phase 4: 用户验收测试 (UAT)              [Day 5 下午]
  ↓
Phase 5: 压力测试 (Stress Tests)         [Day 6 上午]
  ↓
上线部署                                  [Day 6 下午]
```

### 15.2 详细测试用例

#### **T1: 单元测试 - 数据模型层**

```python
# tests/test_models_postgres.py
"""
PostgreSQL 特定模型测试
验证数据类型映射、约束、默认值
"""

import pytest
from django.test import TestCase
from decimal import Decimal
from django.utils import timezone
from pgvector.django import VectorField


class TestPostgreSQLDataTypes(TestCase):
    """测试 PostgreSQL 特有数据类型"""
    
    def test_inet_field_storage(self):
        """测试 IP 地址字段 (INET 类型)"""
        from cmdb.models import Server
        server = Server.objects.create(
            hostname='test-server',
            ip_address='192.168.1.100',  # IPv4
            port=22,
            username='root',
            cpu_cores=4,
            memory_gb=16
        )
        
        retrieved = Server.objects.get(pk=server.pk)
        self.assertEqual(retrieved.ip_address, '192.168.1.100')
        
        # 测试 IPv6
        server.ip_address = '2001:db85::8a2e:370:7334'
        server.save()
        self.assertTrue(str(server.ip_address).startswith('2001'))
    
    def test_jsonb_field_operations(self):
        """测试 JSONB 字段的高级查询"""
        from script_manager.models import TaskExecution, Script
        
        script = Script.objects.create(
            name='Test Script',
            script_type='sh',
            content='echo "Hello"',
            description='Test'
        )
        
        execution = TaskExecution.objects.create(
            script=script,
            user='admin',
            params={'port': 8080, 'debug': True, 'servers': ['web1', 'web2']},
            concurrency=5,
            timeout=60
        )
        
        # JSONB 包含查询
        results = TaskExecution.objects.filter(params__contains={'port': 8080})
        self.assertEqual(results.count(), 1)
        
        # JSONB 键查询
        results = TaskExecution.objects.filter(params__has_key='debug')
        self.assertEqual(results.count(), 1)
    
    def test_array_field_support(self):
        """测试 PostgreSQL 数组类型 (未来扩展)"""
        # 示例: 如果使用了 ArrayField
        pass
    
    def test_timestamptz_timezone(self):
        """测试带时区的时间戳"""
        from cmdb.models import Server
        
        now = timezone.now()
        server = Server.objects.create(
            hostname='tz-test',
            ip_address='10.0.0.1',
            username='root',
            cpu_cores=2,
            memory_gb=4
        )
        
        # 验证存储的是 aware datetime
        self.assertTrue(timezone.is_aware(server.created_at))
        
        # 验证自动转换为 UTC
        self.assertIn('+00:00', str(server.created_at))


class TestEncryptedFieldsPostgres(TestCase):
    """测试加密字段在 PostgreSQL 中的行为"""
    
    def test_fernet_field_roundtrip(self):
        """加密 -> 存储 -> 读取 -> 解密 循环"""
        from cmdb.models import Server
        
        original_password = 'SuperSecretPassword123!'
        server = Server.objects.create(
            hostname='encrypt-test',
            ip_address='172.16.0.1',
            password=original_password,
            username='root',
            cpu_cores=4,
            memory_gb=8
        )
        
        # 从数据库重新读取
        server_from_db = Server.objects.get(pk=server.pk)
        self.assertEqual(server_from_db.password, original_password)
    
    def test_encrypted_field_query(self):
        """测试加密字段的精确查询"""
        from cmdb.models import Server
        
        s1 = Server.objects.create(
            hostname='query-test-1',
            ip_address='10.0.0.10',
            password='password1',
            username='root',
            cpu_cores=2,
            memory_gb=4
        )
        
        s2 = Server.objects.create(
            hostname='query-test-2',
            ip_address='10.0.0.11',
            password='password2',
            username='root',
            cpu_cores=2,
            memory_gb=4
        )
        
        # 按密码查询 (Fernet 支持精确匹配)
        results = Server.objects.filter(password='password1')
        self.assertEqual(results.count(), 1)
        self.assertEqual(results.first().hostname, 'query-test-1')


class TestConstraintsAndIndexes(TestCase):
    """测试约束和索引"""
    
    def test_unique_constraint(self):
        """测试唯一约束"""
        from cmdb.models import Server
        
        Server.objects.create(
            hostname='unique-test',
            ip_address='192.168.255.1',
            username='root',
            cpu_cores=2,
            memory_gb=4
        )
        
        # 重复 IP 应该抛出 IntegrityError
        with self.assertRaises(Exception):  # IntegrityError
            Server.objects.create(
                hostname='unique-test-2',
                ip_address='192.168.255.1',  # 重复!
                username='root',
                cpu_cores=2,
                memory_gb=4
            )
    
    def test_foreign_key_constraint(self):
        """测试外键约束"""
        from django.db import IntegrityError
        from cmdb.models import TerminalLog
        from system.models import User
        
        user = User.objects.create_user(username='fk_test', password='pass123')
        
        # 有效的外键
        log = TerminalLog.objects.create(
            user=user,
            channel_name='test_channel'
        )
        self.assertIsNotNone(log.pk)
        
        # 无效的外键 (用户不存在)
        with self.assertRaises(IntegrityError):
            TerminalLog.objects.create(
                user_id=999999,  # 不存在的用户
                channel_name='bad_channel'
            )


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
```

#### **T2: 集成测试 - 核心功能流**

```python
# tests/test_integration_postgres.py
"""
端到端集成测试
模拟真实用户操作流程
"""

import pytest
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from unittest.mock import patch, MagicMock


class TestUserAuthenticationFlow(TestCase):
    """用户认证集成测试"""
    
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username='integration_test',
            password='SecurePass123!',
            phone='13800138000',
            department='IT部'
        )
    
    def test_login_flow(self):
        """测试完整登录流程"""
        # 1. 访问登录页
        response = self.client.get('/login/')
        self.assertEqual(response.status_code, 200)
        
        # 2. 提交登录表单
        response = self.client.post('/login/', {
            'username': 'integration_test',
            'password': 'SecurePass123!'
        })
        self.assertRedirects(response, '/')
        
        # 3. 验证会话已创建
        self.assertIn('_auth_user_id', self.client.session)
    
    @patch('system.auth_backend.LDAPBackend.authenticate')
    def test_ldap_authentication(self, mock_ldap):
        """测试 LDAP 认证流程"""
        mock_ldap.return_value = self.user
        
        response = self.client.post('/login/', {
            'username': 'ldap_user',
            'password': 'ldap_pass'
        })
        
        mock_ldap.assert_called_once()
        self.assertRedirects(response, '/')


class TestCMDBWorkflow(TestCase):
    """资产管理工作流测试"""
    
    def setUp(self):
        self.client = Client()
        self.admin = get_user_model().objects.create_superuser(
            username='admin_test',
            password='AdminPass123!',
            email='admin@test.com'
        )
        self.client.force_login(self.admin)
    
    def test_server_lifecycle(self):
        """测试服务器完整生命周期"""
        from cmdb.models import Server, ServerGroup
        
        # 1. 创建分组
        group = ServerGroup.objects.create(name='Test Group')
        
        # 2. 创建服务器
        response = self.client.post('/cmdb/servers/add/', {
            'hostname': 'web-server-01',
            'ip_address': '10.0.0.50',
            'port': 22,
            'username': 'ubuntu',
            'password': 'UbuntuPass123!',
            'cpu_cores': 8,
            'memory_gb': 32,
            'os_name': 'Ubuntu 22.04 LTS',
            'group': group.id
        })
        self.assertRedirects(response, '/cmdb/servers/')
        
        # 3. 验证创建成功
        server = Server.objects.get(ip_address='10.0.0.50')
        self.assertEqual(server.hostname, 'web-server-01')
        self.assertEqual(server.group, group)
        
        # 4. 编辑服务器
        response = self.client.post(f'/cmdb/servers/edit/{server.id}/', {
            'hostname': 'web-server-01-updated',
            'ip_address': '10.0.0.50',
            'port': 22,
            'username': 'ubuntu',
            'password': 'NewPass456!',
            'cpu_cores': 16,
            'memory_gb': 64,
            'os_name': 'Ubuntu 22.04 LTS',
            'group': group.id
        })
        self.assertRedirects(response, '/cmdb/servers/')
        
        server.refresh_from_db()
        self.assertEqual(server.cpu_cores, 16)
        self.assertEqual(server.memory_gb, 64)
        
        # 5. 删除服务器
        response = self.client.post(f'/cmdb/servers/delete/{server.id}/')
        self.assertRedirects(response, '/cmdb/servers/')
        
        with self.assertRaises(Server.DoesNotExist):
            Server.objects.get(pk=server.id)


class TestWebSSHIntegration(TestCase):
    """WebSSH 集成测试 (Mock SSH)"""
    
    @patch('paramiko.SSHClient.connect')
    @patch('paramiko.SSHClient.invoke_shell')
    def test_webssh_connection(self, mock_shell, mock_connect):
        """测试 WebSocket SSH 连接建立"""
        # Mock setup
        mock_shell.return_value = MagicMock()
        mock_connect.return_value = None
        
        from channels.testing import WebsocketCommunicator
        from cmdb.consumers import SSHConsumer
        
        # This would require a more complex async test setup
        # Simplified version here
        pass


class TestAIModuleIntegration(TestCase):
    """AI 功能集成测试"""
    
    @patch('ai_ops.utils.ask_ai')
    def test_server_diagnosis_flow(self, mock_ai):
        """测试服务器诊断流程"""
        from cmdb.models import Server, ServerMetric
        from system.models import User
        import datetime
        
        # 准备测试数据
        user = User.objects.create_user(username='ai_test', password='pass')
        server = Server.objects.create(
            hostname='diag-server',
            ip_address='10.0.0.100',
            username='root',
            cpu_cores=4,
            memory_gb=16
        )
        
        # 插入模拟监控数据
        for i in range(20):
            ServerMetric.objects.create(
                server=server,
                cpu_usage=85.0 + (i % 10),
                mem_usage=90.0,
                disk_usage=70.0,
                load_1min=2.5,
                net_in=1024.0,
                net_out=2048.0
            )
        
        # Mock AI 响应
        mock_ai.return_value = {
            'content': 'CPU 使用率偏高 (85%)，建议检查高负载进程...'
        }
        
        # 执行诊断请求
        self.client.force_login(user)
        response = self.client.post(f'/ai/diagnose/{server.id}/', {
            'model_id': 1
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['status'])
        self.assertIn('CPU', data['analysis'])
```

#### **T3: 性能基准测试**

```python
# tests/test_performance_benchmark.py
"""
PostgreSQL vs SQLite 性能基准对比
"""

import time
import statistics
from django.test import TestCase
from django.db import connection
from cmdb.models import Server, ServerMetric


class TestQueryPerformance(TestCase):
    """查询性能基准测试"""
    
    @classmethod
    def setUpTestData(cls):
        """批量生成测试数据"""
        print("\n📊 生成测试数据...")
        start = time.time()
        
        # 创建 100 台服务器
        servers = [
            Server(
                hostname=f'server-{i:04d}',
                ip_address=f'10.0.{i//256}.{i%256}',
                username='root',
                cpu_cores=4,
                memory_gb=16
            )
            for i in range(100)
        ]
        Server.objects.bulk_create(servers)
        
        # 为每台服务器插入 1000 条监控数据 (共 10万条)
        metrics = []
        all_servers = list(Server.objects.all())
        for server in all_servers:
            for j in range(1000):
                metrics.append(ServerMetric(
                    server=server,
                    cpu_usage=50.0 + (j % 50),
                    mem_usage=60.0 + (j % 40),
                    disk_usage=70.0,
                    load_1min=1.5,
                    net_in=1000.0,
                    net_out=2000.0
                ))
        
        ServerMetric.objects.bulk_create(metrics, batch_size=1000)
        
        elapsed = time.time() - start
        print(f"  ✅ 数据生成完成: {len(all_servers)} 服务器, {len(metrics)} 指标, 耗时 {elapsed:.2f}s")
    
    def test_simple_select_performance(self):
        """简单 SELECT 查询性能"""
        times = []
        
        for _ in range(10):
            start = time.perf_counter()
            list(Server.objects.all()[:100])
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)
        
        avg_ms = statistics.mean(times)
        p99_ms = sorted(times)[int(len(times) * 0.99)]
        
        print(f"\n  📈 Server 列表查询 (100条):")
        print(f"     平均: {avg_ms:.2f}ms | P99: {p99_ms:.2f}ms")
        
        self.assertLess(avg_ms, 50, "平均查询时间应 < 50ms")
        self.assertLess(p99_ms, 100, "P99 查询时间应 < 100ms")
    
    def test_filtered_query_performance(self):
        """带过滤条件的查询性能"""
        times = []
        target_server = Server.objects.first()
        
        for _ in range(10):
            start = time.perf_counter()
            list(ServerMetric.objects.filter(
                server=target_server
            ).order_by('-created_at')[:100])
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)
        
        avg_ms = statistics.mean(times)
        print(f"\n  📈 ServerMetric 过滤查询 (100条):")
        print(f"     平均: {avg_ms:.2f}ms")
        
        self.assertLess(avg_ms, 30, "过滤查询应 < 30ms")
    
    def test_join_query_performance(self):
        """JOIN 查询性能"""
        times = []
        
        for _ in range(10):
            start = time.perf_counter()
            list(Server.objects.select_related('group').all()[:50])
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)
        
        avg_ms = statistics.mean(times)
        print(f"\n  📈 JOIN 查询 (Server+Group, 50条):")
        print(f"     平均: {avg_ms:.2f}ms")
        
        self.assertLess(avg_ms, 20, "JOIN 查询应 < 20ms")
    
    def test_write_performance(self):
        """写入性能测试"""
        server = Server.objects.last()
        
        start = time.perf_counter()
        metrics = [
            ServerMetric(
                server=server,
                cpu_usage=75.0,
                mem_usage=80.0,
                disk_usage=65.0,
                load_1min=2.0,
                net_in=1500.0,
                net_out=2500.0
            )
            for _ in range(1000)
        ]
        ServerMetric.objects.bulk_create(metrics)
        elapsed = (time.perf_counter() - start) * 1000
        
        throughput = 1000 / (elapsed / 1000)  # records per second
        print(f"\n  📈 批量写入 (1000条):")
        print(f"     总耗时: {elapsed:.2f}ms | 吞吐: {throughput:.0f} records/s")
        
        self.assertLess(elapsed, 500, "1000条批量写入应 < 500ms")
        self.assertGreater(throughput, 2000, "吞吐应 > 2000 rec/s")


class TestConcurrencyPerformance(TestCase):
    """并发性能测试"""
    
    def test_concurrent_reads(self):
        """并发读测试"""
        import threading
        import queue
        
        results = queue.Queue()
        
        def read_task():
            start = time.perf_counter()
            list(Server.objects.all()[:50])
            elapsed = (time.perf_counter() - start) * 1000
            results.put(elapsed)
        
        threads = [threading.Thread(target=read_task) for _ in range(20)]
        
        start = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        total_elapsed = (time.perf_counter() - start) * 1000
        
        times = [results.get() for _ in range(20)]
        avg_ms = statistics.mean(times)
        max_ms = max(times)
        
        print(f"\n  📈 并发读取 (20线程):")
        print(f"     总耗时: {total_elapsed:.2f}ms")
        print(f"     平均延迟: {avg_ms:.2f}ms | 最大延迟: {max_ms:.2f}ms")
        
        self.assertLess(total_elapsed, 200, "20个并发读应在 200ms 内完成")


# 运行性能测试
if __name__ == '__main__':
    import django
    from django.test.utils import get_runner
    from django.conf import settings
    
    django.setup()
    TestRunner = get_runner(settings)
    test_runner = TestRunner(verbosity=2)
    failures = test_runner.run_tests(['__main__'])
```

#### **T4: 压力测试 (Locust)**

```python
# locustfile.py
"""
Locust 压力测试脚本
模拟多用户并发访问
"""

from locust import HttpUser, task, between
import random
import string


class AiOpsUser(HttpUser):
    """模拟 AiOps 平台用户"""
    
    wait_time = between(1, 3)  # 每次操作间隔 1-3 秒
    
    def on_start(self):
        """用户登录"""
        self.client.post("/login/", {
            "username": "perf_test_user",
            "password": "TestPass123!"
        })
    
    @task(3)
    def view_dashboard(self):
        """访问仪表盘 (最频繁的操作)"""
        self.client.get("/")
    
    @task(2)
    def view_server_list(self):
        """浏览服务器列表"""
        self.client.get("/cmdb/servers/")
    
    @task(2)
    def view_k8s_clusters(self):
        """查看 K8s 集群列表"""
        self.client.get("/k8s/clusters/")
    
    @task(1)
    def view_audit_logs(self):
        """查看审计日志"""
        self.client.get("/cmdb/logs/")
    
    @task(1)
    def view_scripts(self):
        """浏览脚本库"""
        self.client.get("/script/scripts/")


# 运行压力测试
# locust -f locustfile.py --host=http://localhost:8000 --users 100 --spawn-rate 10
```

### 15.3 测试执行计划

```bash
# ====================================
# 完整测试套件执行脚本
# ====================================

#!/bin/bash
# run_full_test_suite.sh

set -e

echo "========================================="
echo "🧪 AiOps PostgreSQL 迁移测试套件"
echo "========================================="

# 1. 单元测试
echo "\n[1/5] 运行单元测试..."
python manage.py test tests.test_models_postgres -v 2
echo "✅ 单元测试完成"

# 2. 集成测试
echo "\n[2/5] 运行集成测试..."
python manage.py test tests.test_integration_postgres -v 2
echo "✅ 集成测试完成"

# 3. 性能基准测试
echo "\n[3/5] 运行性能基准..."
python tests/test_performance_benchmark.py
echo "✅ 性能测试完成"

# 4. Django 系统检查
echo "\n[4/5] Django 系统检查..."
python manage.py check --deploy
python manage.py check --database default
echo "✅ 系统检查完成"

# 5. 数据验证
echo "\n[5/5] 运行数据验证..."
python scripts/post_migration_validation.py
echo "✅ 数据验证完成"

echo "\n========================================="
echo "🎉 所有测试通过! 可以准备上线"
echo "========================================="
```

---

## 16. 性能优化建议

### 16.1 索引优化策略

```sql
-- ====================================
-- 推荐的生产环境索引配置
-- 在迁移完成后执行
-- ====================================

-- 1. ServerMetric 复合索引 (高频查询)
CREATE INDEX CONCURRENTLY idx_metric_server_time 
ON cmdb_servermetric (server_id, created_at DESC);

-- 2. 最近数据部分索引 (加速 Dashboard)
CREATE INDEX CONCURRENTLY idx_metric_recent 
ON cmdb_servermetric (created_at DESC)
WHERE created_at > NOW() - INTERVAL '7 days';

-- 3. TerminalLog 用户+时间索引 (审计查询)
CREATE INDEX CONCURRENTLY idx_terminallog_user_time 
ON cmdb_terminallog (user_id, start_time DESC);

-- 4. HighRiskAudit 全文搜索索引
CREATE INDEX CONCURRENTLY idx_highrisk_cmd_trgm 
ON cmdb_highriskaudit USING gin (command gin_trgm_ops);

-- 5. ChatMessage 会话索引 (对话加载)
CREATE INDEX CONCURRENTLY idx_chatmsg_session_created 
ON ai_ops_chatmessage (session_id, created_at ASC);

-- 6. TaskLog 执行状态索引
CREATE INDEX CONCURRENTLY idx_tasklog_status 
ON script_manager_tasklog (status, execution_id);

-- 7. NodeSnapshot 集群+节点唯一索引 (已有，验证)
-- UNIQUE(cluster_token, node_name)

-- 8. ConfigMapHistory 版本索引
CREATE INDEX CONCURRENTLY idx_configmap_ver 
ON k8s_manager_configmaphistory (cluster_id, namespace, name, version DESC);
```

### 16.2 查询优化示例

```python
# optimizations/query_hints.py
"""
PostgreSQL 查询优化技巧
"""

from django.db.models import Prefetch, Q
from django.db import connection
from django.views.decorators.cache import cache_page


def optimized_dashboard(request):
    """优化的仪表盘查询"""
    from cmdb.models import Server, ServerMetric
    from django.core.cache import cache
    from django.db.models import Avg, Max, Subquery, OuterRef
    
    # 1. 使用 select_related 减少 JOIN 次数
    servers = Server.objects.select_related('group').only(
        'hostname', 'ip_address', 'status', 'group__name',
        'cpu_cores', 'memory_gb'
    )[:50]
    
    # 2. 使用 Subquery 获取最新指标 (避免 N+1 查询)
    latest_metric_subq = Subquery(
        ServerMetric.objects.filter(
            server=OuterRef('pk')
        ).order_by('-created_at')[:1].values('cpu_usage', 'mem_usage')
    )
    
    servers_with_metrics = servers.annotate(
        latest_cpu=latest_metric_subq.values('cpu_usage'),
        latest_mem=latest_metric_subq.values('mem_usage')
    )
    
    # 3. 使用缓存 (Dashboard 数据变化不频繁)
    cache_key = f'dashboard_servers_{request.user.id}'
    result = cache.get(cache_key)
    
    if not result:
        result = list(servers_with_metrics)
        cache.set(cache_key, result, timeout=60)  # 缓存 60 秒
    
    return {'servers': result}


@cache_page(60 * 5)  # 页面缓存 5 分钟
def cached_server_list(request):
    """缓存的服务器列表 (适合只读页面)"""
    from cmdb.models import Server
    return {'servers': Server.objects.all()}


def efficient_log_search(query, page=1):
    """高效的审计日志搜索 (使用全文搜索)"""
    from cmdb.models import HighRiskAudit
    
    if query:
        # PostgreSQL 全文搜索 (比 LIKE 快 100x)
        results = HighRiskAudit.objects.filter(
            command__trigram_similar=query  # 需要 pg_trgm 扩展
        ).select_related('user', 'server')
    else:
        results = HighRiskAudit.objects.all().select_related('user', 'server')
    
    # 分页
    paginator = Paginator(results, 20)
    page_obj = paginator.page(page)
    
    return page_obj
```

### 16.3 数据库连接池配置

```python
# settings.py 末尾添加

# ====================================
# 连接池配置 (生产环境必须!)
# ====================================

# 方案 1: Django 内置连接持久化 (简单)
DATABASES['default']['CONN_MAX_AGE'] = 60  # 复用连接 60 秒
DATABASES['default']['CONN_HEALTH_CHECKS'] = True  # Django 4.1+

# 方案 2: django-db-geventpool (协程池)
# pip install django-db-geventpool
# DATABASES['default']['ENGINE'] = 'django_geventpool.backends.postgresql_psycopg2'
# DATABASES['default']['OPTIONS'] = {
#     'MAX_CONNS': 20,
#     'REUSE_CONNS': 10
# }

# 方案 3: PgBouncer (外部连接池，推荐高并发)
# 修改 DB_HOST 为 PgBouncer 地址
# DATABASES['default']['HOST'] = 'localhost'  # PgBouncer 监听地址
# DATABASES['default']['PORT'] = 6432         # PgBouncer 默认端口
```

---

## 17. 运维监控配置

### 17.1 Prometheus + Grafana 监控栈

```yaml
# docker-compose.monitoring.yml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:v2.45.0
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.retention.time=15d'

  grafana:
    image: grafana/grafana:10.2.0
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/grafana/provisioning:/etc/grafana/provisioning
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD}
      GF_USERS_ALLOW_SIGN_UP: "false"
    depends_on:
      - prometheus

  postgres_exporter:
    image: prometheus/postgres_exporter:v0.15.0
    environment:
      DATA_SOURCE_NAME: "postgresql://aiops_user:${POSTGRES_PASSWORD}@db:5432/aiops_db?sslmode=disable"
    ports:
      - "9187:9187"
    depends_on:
      - db

volumes:
  prometheus_data:
  grafana_data:
```

**Prometheus 配置** (`monitoring/prometheus.yml`):
```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres_exporter:9187']
    scrape_interval: 10s

  - job_name: 'django'
    static_configs:
      - targets: ['web:8000']
    metrics_path: '/metrics'

rule_files:
  - 'alert_rules.yml'
```

### 17.2 关键监控指标

```yaml
# monitoring/alert_rules.yml
groups:
- name: postgresql_alerts
  rules:
  # 连接数告警
  - alert: PostgresHighConnections
    expr: pg_stat_activity_count{datname="aiops_db"} > 80
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "PostgreSQL 连接数过高 ({{ $value }})"
      
  # 慢查询告警
  - alert: PostgresSlowQueries
    expr: increase(pg_stat_statements_total_exec_time[5m]) > 10000000
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "检测到 PostgreSQL 慢查询"
      
  # 数据库大小增长告警
  - alert: DatabaseSizeGrowingFast
    expr: increase(pg_database_size_bytes{datname="aiops_db"}[24h]) > 1073741824  # 1GB/天
    for: 1h
    labels:
      severity: info
    annotations:
      summary: "数据库日增长超过 1GB (当前: {{ $value | humanize1024 }})"
      
  # 死锁检测
  - alert: PostgresDeadlocks
    expr: increase(pg_locks_deadlocks[5m]) > 0
    for: 0m
    labels:
      severity: critical
    annotations:
      summary: "PostgreSQL 检测到死锁!"
```

### 17.3 Grafana Dashboard 推荐

```markdown
## 推荐的 Grafana Dashboard

1. **PostgreSQL Overview** (ID: 9628)
   - 数据库连接数、事务率、缓存命中率
   - 推荐导入: https://grafana.com/grafana/dashboards/9628

2. **PostgreSQL Detailed** (ID: 12736)
   - 表级统计、索引使用、锁等待
   - 推荐导入: https://grafana.com/grafana/dashboards/12736

3. **Django Performance** (自定义)
   - HTTP 请求延迟、错误率、QPS
   - 需要集成 django-prometheus

4. **AiOps 业务指标** (自定义)
   - 服务器数量趋势、SSH 会话数、AI 调用量
   - 需要从业务代码暴露指标

### 关键 Dashboard Panel 配置

| Panel | 指标 | 告警阈值 |
|-------|------|---------|
| Active Connections | `pg_stat_activity_count` | >80 Warning, >95 Critical |
| Query Latency P99 | `pg_stat_statements` | >500ms Warning |
| Cache Hit Ratio | `pg_stat_database_blks_hit / (blks_hit+blks_read)` | <95% Warning |
| Deadlocks/min | `pg_locks_deadlocks` | >0 Critical |
| DB Size Growth | `pg_database_size_bytes` | >1GB/day Info |
| Transaction Rate | `pg_stat_database_xact_commit + xact_rollback` | 监控趋势 |
| Lock Waits | `pg_locks_waiting` | >5 Warning |
```

---

## 18. 附录

### 18.1 迁移时间线总览

```
═══════════════════════════════════════════════════════════════
         AiOps 数据库迁移时间线 (建议: 周末执行)
═══════════════════════════════════════════════════════════════

Day 0 (周五)          Day 1-2 (周末)        Day 3 (周一)
─────────            ─────────────         ─────────
┌──────────────┐   ┌──────────────────┐   ┌──────────────┐
│ 环境准备       │   │ 正式迁移执行      │   │ 测试验证      │
│ • 安装 PG18    │   │ • 停止服务        │   │ • 单元测试     │
│ • PgVector    │   │ • 数据清洗        │   │ • 集成测试     │
│ • 备份数据     │   │ • 导出 SQLite     │   │ • 性能测试     │
│ • 验证脚本     │   │ • 导入 PG        │   │ • UAT 验收    │
│              │   │ • 序列重置        │   │              │
│              │   │ • 初步验证        │   │              │
└──────────────┘   └──────────────────┘   └──────────────┘
     4h                  6-8h                 8h

Day 4-5              Day 6                Day 7+
─────────            ─────────           ─────────
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ 性能优化      │   │ 上线部署      │   │ 生产监控      │
│ • 索引优化    │   │ 切换流量      │   │ • Prometheus  │
│ • 查询调优    │   │ DNS 更新      │   │ • Grafana     │
│ • 连接池配置   │   │ 服务重启      │   │ • 告警规则     │
│              │   │ 功能验证      │   │ • 容量规划     │
└──────────────┘   └──────────────┘   └──────────────┘
     4h               2h               持续

总计预估: 3-4 天 (含测试验证)
停机窗口: 4-8 小时 (数据迁移阶段)
```

### 18.2 快速参考卡 (Cheat Sheet)

```bash
# ====================================
# 📋 迁移操作快速参考卡
# 打印出来贴在显示器旁边!
# ====================================

# 【安装】
docker run -d --name pg18 \
  -e POSTGRES_DB=aiops_db \
  -e POSTGRES_USER=aiops_user \
  -e POSTGRES_PASSWORD='YourPass!' \
  -p 5432:5432 \
  postgres:18-alpine

# 【启用扩展】
psql -U aiops_user -d aiops_db -c "CREATE EXTENSION vector;"
psql -U aiops_user -d aiops_db -c "CREATE EXTENSION pg_trgm;"

# 【备份 SQLite】
cp db.sqlite3 backups/pre_migration_$(date +%Y%m%d)/db.sqlite3.backup

# 【导出数据】
python manage.py dumpdata --natural-foreign --indent 2 > data_export.json

# 【修改配置】
# settings.py → DATABASES 改为 postgresql

# 【创建表结构】
python manage.py migrate

# 【导入数据】
python manage.py loaddata data_export.json

# 【更新序列】
python manage.py sqlsequencereset | python manage.py dbshell

# 【验证】
python scripts/post_migration_validation.py

# 【回滚】(如果需要)
cp backups/pre_migration_*/db.sqlite3.backup db.sqlite3
# 改回 settings.py 为 sqlite3
sudo systemctl restart aiops-daphne
```

### 18.3 常见问题 FAQ

```markdown
## Q&A: 迁移常见问题

### Q1: 迁移需要停机吗?
**A**: 推荐停机迁移，确保数据一致性。停机窗口约 4-8 小时。
如需在线迁移，可考虑使用工具如 [pgloader](https://pgloader.io/) 的 LIVE 模式，
但复杂度较高，不推荐首次迁移使用。

### Q2: 数据量大 (>10GB) 怎么办?
**A**: 
- 使用分批导入 (`batch_loaddata.py`)
- 增加 PostgreSQL `shared_buffers` 和 `work_mem`
- 考虑临时关闭 WAL 日志归档
- 使用 `pg_restore --jobs=4` 并行恢复

### Q3: 加密数据会丢失吗?
**A**: 只要保持 `APP_MASTER_KEY` 一致，Fernet 加密的数据可以正常解密。
**关键**: 务必在 `.env` 或环境变量中保持相同的密钥!

### Q4: Django 版本有要求吗?
**A**: Django 3.2+ 完美支持 PostgreSQL。
本项目使用 Django 5.x，原生支持 JSONB、搜索等特性。

### Q5: PgVector 必须现在就启用吗?
**A**: 不必。可以先完成基础迁移，PgVector 在未来启用 AI 功能时再激活。
但建议提前安装扩展，避免二次停机。

### Q6: 迁移后性能一定会提升吗?
**A**: 大部分场景下会有显著提升，特别是：
- 并发写入场景 (100x+)
- 复杂 JOIN 查询
- 全文搜索
- 大表聚合查询

但如果查询本身没有优化，可能看不到明显改善。建议配合第16章的优化建议。

### Q7: 可以回滚到 SQLite 吗?
**A**: 可以! 本方案提供了完整的回滚流程（第14章）。
关键前提：保留完整的 SQLite 备份文件。

### Q8: WebSocket (Channels) 受影响吗?
**A**: Channels 使用 Redis 作为消息队列层，与数据库无关。
但 Session 后端如果从数据库切换，需确认 Redis 配置正确。
当前项目已使用 Redis 作为 CHANNEL_LAYERS，无影响。

### Q9: Celery 任务队列受影响吗?
**A**: Celery 使用 Redis 作为 Broker，不受数据库切换影响。
但任务结果存储如果使用数据库后端 (django-db)，需确保迁移后正常工作。
当前项目使用 redis 作为 result_backend，无影响。

### Q10: 如何验证迁移完全成功?
**A**: 运行完整的验证清单：
1. `post_migration_validation.py` 自动化验证 ✅
2. 所有单元测试通过 ✅
3. 核心功能人工验收 ✅
4. 性能基准对比达标 ✅
5. 监控告警正常运行 ✅
```

### 18.4 相关资源链接

```markdown
## 参考资源

### 官方文档
- [PostgreSQL 18 文档](https://www.postgresql.org/docs/current/)
- [PgVector 扩展文档](https://github.com/pgvector/pgvector)
- [Django PostgreSQL Notes](https://docs.djangoproject.com/en/stable/ref/databases/#postgresql-notes)
- [psycopg2 文档](https://www.psycopg.org/docs/)
- [Django Channels Deployment](https://channels.readthedocs.io/en/latest/deploying.html)

### 迁移工具
- [Django dumpdata/loaddata](https://docs.djangoproject.com/en/stable/howto/initial-data/)
- [pgloader](https://pgloader.io/) - 高级迁移工具
- [AWS DMS](https://aws.amazon.com/dms/) - 云端迁移服务 (可选)

### 监控运维
- [Prometheus PostgreSQL Exporter](https://github.com/prometheus-community/postgres_exporter)
- [Grafana Dashboards](https://grafana.com/grafana/dashboards/?dataSource=postgres&search=postgres)
- [PgBouncer 文档](https://www.pgbouncer.org/usage.html)

### 性能优化
- [PostgreSQL Performance Blog](https://blog.crunchydata.com/blog)
- [Django Database Optimization](https://docs.djangoproject.com/en/stable/topics/db/optimization/)
- [EXPLAIN ANALYZE 指南](https://www.postgresql.org/docs/current/using-explain.html)

### 社区支持
- [PostgreSQL Reddit](https://www.reddit.com/r/PostgreSQL/)
- [Django Forum](https://forum.djangoproject.com/)
- [PgVector GitHub Issues](https://github.com/pgvector/pgvector/issues)
```

### 18.5 迁移检查清单 (最终版)

```markdown
# ═══════════════════════════════════════════════════════════
#   AiOps SQLite → PostgreSQL 18 最终检查清单
#   请逐项勾选，确保所有步骤已完成!
# ═══════════════════════════════════════════════════════════

## 📦 准备阶段

### 环境准备
- [ ] PostgreSQL 18 已安装并运行
- [ ] PgVector 0.7.x 扩展已安装
- [ ] pg_trgm 扩展已安装 (全文搜索)
- [ ] btree_gin 扩展已安装 (数组索引)
- [ ] psycopg2-binary==2.9.9 已安装
- [ ] Python 环境已激活且依赖完整

### 数据备份
- [ ] SQLite 数据库文件已备份 (.sqlite3.backup)
- [ ] SQL Dump 已导出 (.dump.sql)
- [ ] Django JSON 导出已完成 (.json)
- [ ] SSH 日志目录已备份
- [ ] .env 文件中的密钥已记录
- [ ] 备份文件 MD5 校验通过

### 配置准备
- [ ] settings.py DATABASES 已修改为 PostgreSQL
- [ ] requirements.txt 已添加 psycopg2-binary
- [ ] Docker Compose (如使用) 已更新
- [ ] 环境变量已设置 (DB_HOST, DB_USER 等)
- [ ] APP_MASTER_KEY 已确认一致

## 🔧 执行阶段

### 迁移前
- [ ] 应用服务已停止 (daphne/celery)
- [ ] 迁移前 Checklist 全部通过
- [ ] 数据清洗脚本已执行
- [ ] 当前记录数已记录 (counts_before.txt)

### 数据迁移
- [ ] migrate 创建表结构成功 (~35 张表)
- [ ] dumpdata 导出数据成功
- [ ] loaddata 导入数据成功 (所有模型)
- [ ] sqlsequencereset 序列值已更新
- [ ] 无导入错误或警告

### 迁移后立即验证
- [ ] 各表记录数与迁移前一致
- [ ] 外键完整性验证通过
- [ ] 加密字段解密验证通过
- [ ] 时区字段处理正确
- [ ] JSON 字段升级为 JSONB
- [ ] 特殊类型 (INET) 工作正常

## ✅ 测试阶段

### 自动化测试
- [ ] 单元测试全部通过
- [ ] 集成测试全部通过
- [ ] Django system check 通过
- [ ] Django deploy check 通过

### 手动功能验证
- [ ] 用户登录/登出正常
- [ ] CMDB 服务器 CRUD 正常
- [ ] WebSSH WebSocket 连接正常
- [ ] K8s 集群展示正常
- [ ] 脚本执行正常
- [ ] AI 对话功能正常
- [ ] SSL 证书列表正常

### 性能验证
- [ ] 页面加载时间 < 3 秒
- [ ] API 响应时间 < 500ms
- [ ] 并发 50 用户无报错
- [ ] 数据库连接池正常工作

## 🚀 上线阶段

### 切换上线
- [ ] DNS 已指向新服务器 (如适用)
- [ ] 负载均衡已更新 (如适用)
- [ ] SSL 证书已配置
- [ ] 静态文件已收集 (collectstatic)
- [ ] 缓存已预热

### 监控就绪
- [ ] Prometheus 已运行并抓取指标
- [ ] Grafana Dashboard 已导入
- [ ] 告警规则已配置
- [ ] 告警通知渠道已测试 (钉钉/邮件)
- [ ] 日志收集已配置 (ELK/Loki)

### 文档与交接
- [ ] 迁移报告已编写
- [ ] Runbook 已更新
- [ ] 团队成员已培训
- [ ] 回滚方案已告知值班人员
- [ ] 用户通知已发送 (如有必要)

## 📊 完成确认

- [ ] 所有上述项目已完成 ✓
- [ ] 系统稳定运行 24+ 小时 ✓
- [ ] 无用户投诉或工单 ✓
- [ ] 监控无异常告警 ✓

══════════════════════════════════════════════════════════
  🎉 恭喜! AiOps 数据库迁移成功完成!
══════════════════════════════════════════════════════════
```

---

> **文档结束**
>
> **版本历史**:
> - v1.0 (2026-04-13): 初始版本，完整迁移方案
>
> **维护者**: DevOps Team
> **审核状态**: 待技术评审
> **下次更新**: 迁移完成后根据实际情况修订