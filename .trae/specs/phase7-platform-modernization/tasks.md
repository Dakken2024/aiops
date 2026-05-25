# Tasks

- [x] Task 1: 引入 DRF + JWT 认证体系
  - [x] SubTask 1.1: 安装 djangorestframework 和 djangorestframework-simplejwt
  - [x] SubTask 1.2: 配置 DRF settings（认证类、权限类、分页）
  - [x] SubTask 1.3: 实现 /api/v1/auth/login/ 和 /api/v1/auth/refresh/ 视图
  - [x] SubTask 1.4: 为 monitoring、cmdb 等核心模块创建 DRF ViewSet
  - [x] SubTask 1.5: 配置 API 版本路由 /api/v1/ 和 /api/v2/

- [x] Task 2: Vue3 监控 Dashboard 组件
  - [x] SubTask 2.1: 初始化 Vue3 项目（使用 Vite）
  - [x] SubTask 2.2: 创建 Dashboard 图表组件（ECharts 5）
  - [x] SubTask 2.3: 创建告警列表组件
  - [x] SubTask 2.4: 配置 Django Template 加载 Vue3 构建产物
  - [x] SubTask 2.5: 实现 API 数据获取和自动刷新

- [x] Task 3: 多租户基础实现
  - [x] SubTask 3.1: 创建 Tenant 模型
  - [x] SubTask 3.2: 为核心模型（Server、AlertRule 等）添加 tenant 外键
  - [x] SubTask 3.3: 实现 TenantMiddleware 自动注入租户过滤
  - [x] SubTask 3.4: 在 Admin 后台添加租户管理

- [x] Task 4: 插件系统设计
  - [x] SubTask 4.1: 创建 Plugin 模型
  - [x] SubTask 4.2: 实现插件加载器（动态 import）
  - [x] SubTask 4.3: 定义插件基类（Collector/Notifier/Analyzer/Reporter）
  - [x] SubTask 4.4: 在 Admin 后台添加插件管理页面

# Task Dependencies
- Task 2 依赖 Task 1（Vue3 组件需要 DRF API）
- Task 3 可独立并行
- Task 4 可独立并行
