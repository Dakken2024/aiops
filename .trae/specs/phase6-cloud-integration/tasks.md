# Tasks

- [x] Task 1: 创建 CloudResource 模型和多云适配器基础框架
  - [x] SubTask 1.1: 在 cmdb/models.py 添加 CloudResource 模型
  - [x] SubTask 1.2: 创建 cmdb/cloud_adapters/__init__.py 和 base.py 抽象基类
  - [x] SubTask 1.3: 实现阿里云 AliyunAdapter（ECS 指标采集）
  - [x] SubTask 1.4: 实现腾讯云 TencentAdapter（CVM 指标采集）

- [x] Task 2: 创建混合监控仪表盘 API 和页面
  - [x] SubTask 2.1: 新增 API 视图支持按 provider/region 筛选云资源
  - [x] SubTask 2.2: 修改监控 Dashboard 模板展示云资源分组
  - [x] SubTask 2.3: 添加云资源成本概览卡片（月度趋势）

- [x] Task 3: 实现数据保留策略
  - [x] SubTask 3.1: 在 monitoring/models.py 添加 DataRetentionPolicy 模型
  - [x] SubTask 3.2: 编写数据清理 Celery 任务（daily_cleanup）
  - [x] SubTask 3.3: 编写聚合任务（aggregate_metrics）生成 5m/1h/1d 汇总
  - [x] SubTask 3.4: 在 Admin 后台添加数据保留策略配置页面

- [x] Task 4: 准实时告警优化
  - [x] SubTask 4.1: 修改 Celery Beat 广播间隔为 5s
  - [x] SubTask 4.2: 实现 Redis Pub/Sub 指标变更通知
  - [x] SubTask 4.3: 修改 RuleEvaluator 支持事件驱动评估
  - [x] SubTask 4.4: Agent Push API 支持增量推送（仅变化指标）

- [x] Task 5: Agent 安全加固
  - [x] SubTask 5.1: 实现 HMAC-SHA256 签名验证中间件
  - [x] SubTask 5.2: 实现 IP 白名单校验
  - [x] SubTask 5.3: 更新 AgentToken 模型添加 allowed_ips 字段
  - [x] SubTask 5.4: 修改 Agent Push API 视图集成安全校验

# Task Dependencies
- Task 2 依赖 Task 1
- Task 3 依赖 Task 1（需要 CloudResource 区分本地/云资源）
- Task 4 依赖 Task 3（数据清理与实时性优化可并行）
- Task 5 可独立并行
