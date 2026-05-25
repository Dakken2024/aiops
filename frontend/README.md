# Vue3 监控仪表盘 (Phase 7 Task 2)

## 概述

这是一个基于Vue3构建的现代化监控仪表盘组件，集成到现有的Django项目中。

## 文件结构

```
d:\ETL\aiops\
├── frontend/                          # Vue3前端项目
│   ├── src/
│   │   ├── components/
│   │   │   ├── Dashboard.vue      # 主仪表盘组件
│   │   │   ├── MetricChart.vue    # ECharts图表组件
│   │   │   ├── AlertList.vue   # 告警列表组件
│   │   │   └── ServerList.vue  # 服务器列表组件
│   │   ├── router/
│   │   │   └── index.js          # 路由配置
│   │   ├── api/
│   │   │   └── index.js          # API请求封装
│   │   ├── App.vue
│   │   └── main.js
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── templates/monitoring/
│   └── dashboard_vue.html         # Django模板
└── cmdb/views.py                 # 添加了vue_dashboard_page视图
```

## 快速开始

### 1. 安装依赖

```bash
cd frontend
npm install
```

### 2. 开发模式

```bash
npm run dev
```

### 3. 构建生产版本

```bash
npm run build
```

构建产物会自动输出到 `../static/vue-dist` 目录

### 4. 访问Vue仪表盘

启动Django服务器后访问：
```
http://localhost:8000/monitoring/dashboard/vue/
```

## 功能特性

- **实时数据刷新（5秒自动刷新）
- 服务器状态监控
- 告警列表展示
- ECharts图表可视化
- JWT认证集成
- 响应式设计
- 与现有Django页面完美集成

## API接口

Vue应用通过以下API获取数据：

- `/api/v1/monitoring/dashboard/overview/ - 仪表盘概览
- `/api/v1/monitoring/alerts/ - 告警列表
- `/api/v1/cmdb/servers/ - 服务器列表
