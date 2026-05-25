# 性能优化与可扩展性提升 Spec

## Why
Phase 6-8 完成后，系统功能已非常完善，但存在多项技术债务影响性能和可扩展性：规则评估串行执行导致延迟增大、API 无分页导致大数据量查询内存溢出、异常检测每次从数据库加载历史数据效率低下。这些优化将显著提升系统承载能力。

## What Changes
- 规则评估引擎改为 Celery 并行评估 + 异步分片
- 所有 DRF API 添加分页支持（PageNumberPagination + LimitOffsetPagination）
- 异常检测引入 Redis 缓存时序窗口，减少数据库查询
- RemediationEngine 命令执行改为 Paramiko 远程执行 + 容器化沙箱
- Fernet Key 强制从环境变量读取，移除硬编码

## Impact
- 影响 monitoring 规则评估流程
- 影响所有 DRF API 响应格式（添加分页包装）
- 影响 anomaly_detector 历史数据加载逻辑
- 影响 RemediationEngine 执行方式
- 影响 settings.py 安全配置

## ADDED Requirements

### Requirement: 规则评估并行化
The system SHALL 支持告警规则并行评估，降低规则数量增长带来的延迟。

#### Scenario: 并行规则评估
- **WHEN** Celery Beat 触发规则评估任务
- **THEN** 将规则列表分片为多个批次
- **AND** 每个批次由独立的 Celery Worker 并行执行
- **AND** 评估结果统一汇总到 AlertEvent
- **AND** 单条规则评估延迟 < 2s（无论总规则数）

#### Scenario: 规则分片策略
- **WHEN** 规则数量 > 50 条
- **THEN** 按 server_id 哈希分片，同一服务器的规则在同一批次
- **AND** 支持动态调整分片大小（CHUNK_SIZE 配置）

### Requirement: API 分页优化
The system SHALL 为所有列表 API 添加分页支持，防止大数据量查询导致内存溢出。

#### Scenario: 分页查询
- **WHEN** 调用 /api/v1/monitoring/alert-events/?page=2&page_size=50
- **THEN** 返回第 2 页数据（每页 50 条）
- **AND** 响应包含 count, next, previous, results
- **AND** 默认 page_size=20，最大 page_size=200

#### Scenario: 无分页兼容
- **WHEN** 调用旧版 API 不带分页参数
- **THEN** 仍返回分页格式（page=1 的默认结果）
- **AND** 前端可平滑过渡

### Requirement: 异常检测 Redis 缓存
The system SHALL 使用 Redis 缓存时序窗口数据，减少异常检测对数据库的重复查询。

#### Scenario: 缓存命中
- **WHEN** 异常检测任务需要最近 1 小时指标数据
- **THEN** 优先从 Redis 读取缓存的时序窗口
- **AND** 缓存未命中时从数据库加载并写入 Redis
- **AND** 缓存 TTL 设置为 1 小时

#### Scenario: 缓存更新
- **WHEN** Agent 上报新指标
- **THEN** 同时更新 Redis 时序缓存
- **AND** 保持缓存与数据库最终一致

### Requirement: RemediationEngine 安全执行
The system SHALL 使用 Paramiko 远程执行替代本地 subprocess，消除命令注入风险。

#### Scenario: 远程修复
- **WHEN** 触发自动修复动作（如重启服务）
- **THEN** 通过 Paramiko SSH 连接到目标服务器执行
- **AND** 命令在目标服务器沙箱环境中运行
- **AND** 执行结果通过 SSH 返回

#### Scenario: 容器化沙箱
- **WHEN** 配置启用容器化沙箱
- **THEN** 修复命令在 Docker 容器中执行
- **AND** 容器资源限制（CPU 1核，内存 512MB）
- **AND** 超时自动销毁容器

### Requirement: Fernet Key 安全读取
The system SHALL 强制从环境变量读取 Fernet Key，禁止硬编码默认值。

#### Scenario: 启动校验
- **WHEN** Django 启动时
- **THEN** 检查 FERNET_KEY 环境变量是否存在
- **AND** 不存在时抛出 ImproperlyConfigured 异常
- **AND** 禁止启动

#### Scenario: 密钥生成脚本
- **WHEN** 管理员运行生成脚本
- **THEN** 生成新的 Fernet Key
- **AND** 输出到 .env 文件
- **AND** 提示重启服务

## MODIFIED Requirements

### Requirement: 现有 API 响应格式
- **修改前**: 直接返回列表数据
- **修改后**: 返回分页包装格式 {count, next, previous, results}
- **兼容性**: 前端需适配新格式，但数据结构不变

### Requirement: 现有规则评估流程
- **修改前**: 单线程串行评估所有规则
- **修改后**: Celery 并行分片评估
- **兼容性**: 评估逻辑不变，仅执行方式改变

## REMOVED Requirements
无移除需求。
