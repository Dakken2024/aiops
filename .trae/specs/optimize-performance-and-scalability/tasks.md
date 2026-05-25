# Tasks

- [x] Task 1: 规则评估并行化
  - [x] SubTask 1.1: 修改 RuleEvaluator 支持规则分片
  - [x] SubTask 1.2: 创建 Celery 并行评估任务
  - [x] SubTask 1.3: 配置 Celery Beat 触发并行评估
  - [x] SubTask 1.4: 添加分片大小配置项

- [x] Task 2: API 分页优化
  - [x] SubTask 2.1: 配置 DRF 全局分页器
  - [x] SubTask 2.2: 为所有 ViewSet 添加分页支持
  - [x] SubTask 2.3: 添加自定义分页参数（page_size）
  - [x] SubTask 2.4: 更新 API 文档说明分页格式

- [x] Task 3: 异常检测 Redis 缓存
  - [x] SubTask 3.1: 创建 RedisTimeSeriesCache 工具类
  - [x] SubTask 3.2: 修改 AnomalyDetector 优先读取缓存
  - [x] SubTask 3.3: 修改 Agent Push API 同步更新缓存
  - [x] SubTask 3.4: 添加缓存 TTL 和清理策略

- [x] Task 4: RemediationEngine 安全执行
  - [x] SubTask 4.1: 创建 ParamikoRemoteExecutor 类
  - [x] SubTask 4.2: 创建 DockerSandboxExecutor 类
  - [x] SubTask 4.3: 修改 RemediationEngine 使用新执行器
  - [x] SubTask 4.4: 添加执行器选择配置

- [x] Task 5: Fernet Key 安全读取
  - [x] SubTask 5.1: 修改 settings.py 强制从环境变量读取 FERNET_KEY
  - [x] SubTask 5.2: 创建 generate_fernet_key.py 脚本
  - [x] SubTask 5.3: 更新 .env.example 添加 FERNET_KEY 示例
  - [x] SubTask 5.4: 添加启动校验逻辑

# Task Dependencies
- Task 2 可独立并行
- Task 3 依赖 Task 2（可共用 Redis 配置）
- Task 4 可独立并行
- Task 5 可独立并行
