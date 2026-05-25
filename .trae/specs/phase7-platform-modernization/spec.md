# Phase 7: 平台化与前端现代化 Spec

## Why
当前平台前端基于 Django Templates + Bootstrap 4，交互体验较差，全页刷新频繁。API 仅支持 Session 认证，无法支撑第三方集成和移动端接入。随着用户规模扩大，缺乏多租户隔离能力。

## What Changes
- 引入 Django REST Framework + JWT 认证体系
- 构建 Vue3 监控 Dashboard 组件（渐进式替换）
- 新增 Tenant 模型和多租户中间件
- 新增 Plugin 模型和插件加载机制

## Impact
- 新增 DRF 依赖和 API 路由
- 新增前端 Vue3 构建流程
- 所有核心模型需添加 tenant 字段
- 新增 plugin_manager 应用

## ADDED Requirements

### Requirement: DRF + JWT API 体系
The system SHALL 提供基于 DRF 的 REST API，支持 JWT Token 认证和 API 版本管理。

#### Scenario: JWT 认证
- **WHEN** 用户调用 /api/v1/auth/login/
- **THEN** 返回 access_token 和 refresh_token
- **AND** 后续请求在 Header 中携带 Bearer Token
- **AND** Token 过期后使用 refresh_token 换取新 Token

#### Scenario: API 版本管理
- **WHEN** 访问 /api/v1/monitoring/rules/
- **THEN** 返回 v1 版本的数据格式
- **AND** 访问 /api/v2/monitoring/rules/ 返回增强格式

### Requirement: Vue3 监控 Dashboard
The system SHALL 提供 Vue3 实现的监控仪表盘组件，与现有 Django Template 共存。

#### Scenario: 渐进式替换
- **WHEN** 用户访问 /monitoring/dashboard/
- **THEN** 页面加载 Vue3 组件替代原有图表区域
- **AND** 页面头部/导航仍使用 Django Template
- **AND** Vue3 组件通过 DRF API 获取数据

### Requirement: 多租户基础
The system SHALL 提供多租户数据隔离能力，支持免费/专业/企业版计划。

#### Scenario: 租户隔离
- **WHEN** 用户属于 Tenant A
- **THEN** 只能查看 Tenant A 的服务器和告警
- **AND** 超级管理员可查看所有租户数据

### Requirement: 插件系统
The system SHALL 支持插件化扩展，允许自定义采集器、通知渠道、分析器和报表。

#### Scenario: 插件加载
- **WHEN** 管理员在后台启用插件
- **THEN** 系统动态加载插件入口类
- **AND** 插件按类型注册到对应扩展点

## MODIFIED Requirements

### Requirement: 用户认证
- **修改前**: 仅 Session 认证
- **修改后**: Session + JWT 双认证
- **兼容性**: 现有 Web 页面继续使用 Session，API 使用 JWT

## REMOVED Requirements
无移除需求。
