# Phase 6: 云平台集成与数据管道优化 Spec

## Why
中小企业普遍采用多云架构（阿里云/腾讯云/华为云），但现有 AiOps 平台仅支持本地服务器监控，无法统一监控云资源。同时，ServerMetric 数据量无限增长，缺乏数据保留策略，导致查询性能下降。

## What Changes
- 新增 CloudResource 模型和多云数据适配器（阿里云/腾讯云优先）
- 新增混合监控仪表盘（本地+云统一视图）
- 新增 DataRetentionPolicy 模型和定时清理任务
- WebSocket 推送间隔优化至 5s
- Agent Push API 安全加固（HMAC-SHA256 + IP 白名单）

## Impact
- 新增 cmdb CloudResource 模型
- 新增 monitoring 数据保留策略模块
- 修改 Agent Push API 认证逻辑
- 修改 WebSocket 广播频率

## ADDED Requirements

### Requirement: 多云数据接入
The system SHALL 提供阿里云和腾讯云 CloudMonitor 数据接入能力，将云资源指标统一映射到 ServerMetric 结构。

#### Scenario: 阿里云 ECS 指标采集
- **WHEN** 管理员配置阿里云 CloudAccount
- **THEN** Celery 定时任务拉取 ECS CPU/内存/磁盘/网络指标
- **AND** 指标通过 Unified Metric Normalizer 写入 ServerMetric
- **AND** 关联的 CloudResource 记录 last_sync_at

#### Scenario: 腾讯云 CVM 指标采集
- **WHEN** 管理员配置腾讯云 CloudAccount
- **THEN** Celery 定时任务拉取 CVM 指标
- **AND** 指标统一写入 ServerMetric，provider 字段标记为 tencent

### Requirement: 混合监控仪表盘
The system SHALL 在现有监控 Dashboard 中支持云资源展示，按云厂商/区域/资源类型分组。

#### Scenario: 云资源视图
- **WHEN** 用户访问监控仪表盘
- **THEN** 页面展示本地服务器 + 云资源统一列表
- **AND** 支持按 provider（aliyun/tencent）筛选
- **AND** 支持按 region 分组

### Requirement: 数据保留策略
The system SHALL 提供可配置的数据保留策略，自动清理过期监控数据并保留聚合历史。

#### Scenario: 自动数据清理
- **WHEN** Celery Beat 执行 daily_cleanup 任务
- **THEN** 删除超过 retention_days 的原始 ServerMetric 记录
- **AND** 保留 5分钟/1小时/1天 聚合数据（按策略配置）
- **AND** 记录清理日志（删除数量、耗时）

### Requirement: 准实时告警优化
The system SHALL 优化告警延迟，从 30s 降至 5s，并支持事件驱动规则评估。

#### Scenario: 快速告警
- **WHEN** Agent 上报新指标
- **THEN** Redis Pub/Sub 通知 RuleEvaluator
- **AND** 关联规则立即评估（无需等待 60s 周期）
- **AND** 告警通过 WebSocket 在 5s 内推送至前端

### Requirement: Agent 安全加固
The system SHALL 增强 Agent Push API 安全性，防止未授权访问和数据篡改。

#### Scenario: 安全认证
- **WHEN** Agent 调用 Push API
- **THEN** 校验 Token 有效性
- **AND** 校验 HMAC-SHA256 签名
- **AND** 校验来源 IP 在白名单中
- **AND** 任一校验失败返回 401/403

## MODIFIED Requirements

### Requirement: WebSocket 广播频率
- **修改前**: Celery Beat 每 30s 广播一次指标
- **修改后**: 每 5s 广播一次（可配置）
- **兼容性**: 前端无需修改，仅提升刷新频率

## REMOVED Requirements
无移除需求。
