```
# AiOps 智能运维平台

🚀 **AiOps** 是一个基于 Django + Channels 开发的现代化智能运维平台。它集成了资产管理 (CMDB)、WebSSH、Kubernetes 多集群管理、数据库审计以及强大的 AI 赋能功能（故障诊断、智能审计、代码优化）。

🤖 旨在通过 AI 技术降低运维门槛，实现从“被动运维”到“智能辅助”的转型。

---

## ✨ 核心功能

### 🤖 AI 智能运维 (AIOps)

- **多模型支持**：后台可配置多个 AI 模型，支持接入 OpenAI (GPT-4)、DeepSeek (V3/R1)、阿里通义千问等。
- **服务器故障诊断**：一键分析服务器 CPU、内存、磁盘、负载及网络流量趋势，给出优化建议。
- **K8s 深度诊断**：结合 Pod 状态、Events、实时日志及 Java 线程堆栈 (jstack)，自动分析 OOM、死锁及启动失败原因。
- **WebSSH 智能审计**：自动分析录像日志，识别 `rm -rf` 等高危操作并进行安全评分。

### ☸️ Kubernetes 管理

- **多集群管理**：支持导入 KubeConfig 纳管多个 K8s 集群，支持一键切换。
- **全资源监控**：覆盖 Pod、Deployment、StatefulSet、DaemonSet、Service、Ingress。
- **Web Shell & 日志**：浏览器直接进入容器终端，支持实时日志查看。
- **YAML 智能分析**：在线编辑 YAML 创建资源，提交前 AI 自动审计安全隐患。
- **扩缩容**：可视化调整 Deployment 副本数。

### 🖥️ 资产与监控 (CMDB)

- **混合采集模式**：
  - **Agentless (SSH)**：无侵入，服务端通过 SSH 远程拉取指标。
  - **Agent 模式**：提供一键批量下发 Agent 功能，支持内网穿透上报数据。
- **实时监控**：CPU、内存、磁盘、网络流量 (I/O)、负载仪表盘。
- **WebSSH**：基于 xterm.js + WebSocket，支持文件 SFTP 上传/下载、全量操作录像，高危操作预警。
- **云同步**：一键同步阿里云/腾讯云 ECS 实例信息。

### 🛠️ 运维工具

- **脚本管理**：Shell/Python 脚本库，支持 AI 代码优化、批量并发执行、实时日志回显。
- **RBAC 权限**：精确到数据级的权限控制（角色 -> 服务器分组），普通用户与管理员视图隔离。

---

## 🛠️ 技术栈

- **后端**：Python 3.9+, Django 4.x
- **异步/WebSocket**：Django Channels, Daphne
- **任务调度**：APScheduler (去 Redis 化设计，轻量级后台进程)
- **SSH 交互**：Paramiko
- **K8s 交互**：Kubernetes Python Client
- **前端**：Django Templates, AdminLTE 3, Bootstrap 4, ECharts 5, Xterm.js, Ace Editor, Marked.js
- **数据库**：MySQL 5.7+ (生产环境), SQLite (开发环境自动切换)

---

## 🚀 部署指南

### 本地开发环境运行

#### 安装依赖

```bash
pip install -r requirements.txt
```

#### 初始化数据库

```bash
python reset_db.py
python manage.py createsuperuser
```

#### 启动 Web 服务 (Daphne)

```bash
daphne -b 0.0.0.0 -p 8000 ops_platform.asgi:application
```

#### 启动监控采集进程

```bash
python manage.py run_agent
```

#### 启动 Celery

```bash
celery -A ops_platform worker -l debug -P eventlet
```

#### K8s Node 节点采集

```bash
# 修改 agent.yaml 中的 Django 地址和 CLUSTER_TOKEN（CLUSTER_TOKEN 在 K8s 配置管理中获取）
kubectl apply -f agent.yaml
python manage.py collect_k8s
```

---

## ⚙️ 初始化配置指南 (首次运行必读)

系统首次启动后是空的，请按以下顺序配置：

### 1. 配置 AI 模型 (让智能功能生效)

进入 **系统设置 -> AI 模型配置**。

添加模型（以 DeepSeek 为例）：

```
名称: DeepSeek
模型标识: deepseek-chat
Base URL: https://api.deepseek.com
API Key: sk-xxxxxxxx
```

### 2. 录入服务器 (开启监控)

进入 **服务器管理 -> 主机列表**。

点击 **手动录入**，填写 IP、SSH 端口、账号、密码。

**Agent 部署 (可选)**：勾选服务器，点击 “批量安装 Agent”，系统会自动 SSH 上去部署采集插件。

### 3. 配置 K8s 集群

进入 **K8s 容器管理 -> 集群配置**。

粘贴 `~/.kube/config` 文件的完整内容。

保存后即可在 Pod 列表中看到集群资源。

---

## 📁 项目目录结构

```
ops_platform/
├── ops_platform/      # 核心配置 (Settings, ASGI, URL)
├── system/            # 用户、角色、仪表盘、全局配置
├── cmdb/              # 资产、SSH、监控 Agent、审计、文件传输
├── k8s_manager/       # Kubernetes 多集群管理、AI 诊断
├── script_manager/    # 脚本库、批量执行、AI 优化
├── ai_ops/            # AI 接口封装、对话平台、模型管理
├── templates/         # 前端 HTML 模板
│   ├── base.html      # 全局布局
│   ├── index.html     # 仪表盘
│   ├── cmdb/          # 资产相关模板
│   ├── k8s/           # K8s 相关模板
│   └── ...
├── client_dist/       # Agent 客户端脚本
├── manage.py
└── requirements.txt
```

---

## 📝 贡献指南

欢迎贡献代码、文档或提出建议！请遵循以下步骤：

1. Fork 本仓库
2. 创建新分支 (`git checkout -b feature/your-feature`)
3. 提交更改 (`git commit -am 'Add some feature'`)
4. 推送分支 (`git push origin feature/your-feature`)
5. 创建 Pull Request

---

## 📄 许可证

本项目采用 MIT License，请参阅 [LICENSE](LICENSE) 文件获取详细信息。

---

## 📞 联系我们

如有问题或建议，请提交 Issue 或联系项目维护者。

---

🌟 感谢使用 AiOps 智能运维平台！
```