# Tasks

- [x] Task 1: 创建 PostgreSQL 18 Docker 开发环境配置
  - [x] SubTask 1.1: 编写 docker-compose.yml 添加 postgres:18-alpine 服务
  - [x] SubTask 1.2: 编写 postgres/init.sql 自动创建扩展 (vector, pg_trgm, btree_gin)
  - [x] SubTask 1.3: 验证 Docker 环境可正常启动并连接

- [x] Task 2: 修改 Django 数据库配置支持双模式
  - [x] SubTask 2.1: 修改 settings.py 从环境变量读取 DATABASES 配置
  - [x] SubTask 2.2: 添加 PostgreSQL 专属优化参数 (CONN_MAX_AGE, statement_timeout)
  - [x] SubTask 2.3: 保留 SQLite fallback 配置用于开发环境
  - [x] SubTask 2.4: 更新 .env.example 添加 PostgreSQL 相关变量

- [x] Task 3: 更新 Python 依赖
  - [x] SubTask 3.1: 在 requirements.txt 添加 psycopg2-binary==2.9.9
  - [x] SubTask 3.2: 验证依赖安装成功

- [x] Task 4: 创建数据迁移脚本
  - [x] SubTask 4.1: 编写 pre_migration_cleanup.py 数据清洗脚本
  - [x] SubTask 4.2: 编写 batch_loaddata.py 支持分批导入和断点续传
  - [x] SubTask 4.3: 编写 migrate.sh / migrate.ps1 一键迁移脚本

- [x] Task 5: 创建数据验证脚本
  - [x] SubTask 5.1: 编写 post_migration_validation.py 自动化验证
  - [x] SubTask 5.2: 验证覆盖表记录数、外键、加密字段、时区、JSONB、INET

- [x] Task 6: 创建回滚脚本
  - [x] SubTask 6.1: 编写 rollback.sh / rollback.ps1 回滚脚本
  - [x] SubTask 6.2: 支持迁移过程中回滚和迁移完成后回滚两种场景

- [x] Task 7: 性能优化索引
  - [x] SubTask 7.1: 编写 create_indexes.sql 创建推荐索引
  - [x] SubTask 7.2: 编写 query_optimizations.py 查询优化示例

- [x] Task 8: 监控配置
  - [x] SubTask 8.1: 编写 docker-compose.monitoring.yml 部署 Prometheus + Grafana
  - [x] SubTask 8.2: 编写 prometheus.yml 和 alert_rules.yml
  - [x] SubTask 8.3: 提供 Grafana Dashboard JSON 配置

# Task Dependencies
- Task 2 依赖 Task 1（需要 PostgreSQL 环境测试配置）
- Task 4 依赖 Task 2 和 Task 3
- Task 5 依赖 Task 4
- Task 6 依赖 Task 4
- Task 7 依赖 Task 5
- Task 8 依赖 Task 7
