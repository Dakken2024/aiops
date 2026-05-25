import { Activity, Cpu, Server, Wrench, Zap, Shield, Database, Network } from 'lucide-react';

const features = [
  {
    icon: Activity,
    title: 'AIOps 智能监控',
    description: '内置 Z-Score、IQR、移动平均等 6+ 种异常检测算法，AI 驱动的智能诊断引擎',
    color: 'from-indigo-500 to-purple-500',
    bgColor: 'bg-indigo-500/10',
    borderColor: 'border-indigo-500/30'
  },
  {
    icon: Cpu,
    title: 'Kubernetes 管理',
    description: '多集群管理，全资源覆盖，Web Shell 容器终端，实时日志查看',
    color: 'from-cyan-500 to-blue-500',
    bgColor: 'bg-cyan-500/10',
    borderColor: 'border-cyan-500/30'
  },
  {
    icon: Server,
    title: 'CMDB 资产管理',
    description: 'Agentless SSH 远程采集，实时指标监控，云资源一键同步',
    color: 'from-green-500 to-emerald-500',
    bgColor: 'bg-green-500/10',
    borderColor: 'border-green-500/30'
  },
  {
    icon: Wrench,
    title: '运维工具集',
    description: '脚本管理、RBAC 权限、SSL 证书管理，一站式运维解决方案',
    color: 'from-orange-500 to-red-500',
    bgColor: 'bg-orange-500/10',
    borderColor: 'border-orange-500/30'
  },
  {
    icon: Zap,
    title: '告警关联聚类',
    description: '基于时间窗口和服务拓扑的 Correlator，自动聚合级联告警',
    color: 'from-purple-500 to-pink-500',
    bgColor: 'bg-purple-500/10',
    borderColor: 'border-purple-500/30'
  },
  {
    icon: Shield,
    title: '自动修复引擎',
    description: '危险操作确认 + 自动执行修复脚本，提高运维效率',
    color: 'from-blue-500 to-cyan-500',
    bgColor: 'bg-blue-500/10',
    borderColor: 'border-blue-500/30'
  },
  {
    icon: Database,
    title: '运维知识库',
    description: 'AI 智能推荐匹配的 Runbook 条目，沉淀运维经验',
    color: 'from-emerald-500 to-teal-500',
    bgColor: 'bg-emerald-500/10',
    borderColor: 'border-emerald-500/30'
  },
  {
    icon: Network,
    title: '服务拓扑追踪',
    description: '维护服务间依赖关系图，支持影响分析和故障传播路径可视化',
    color: 'from-pink-500 to-rose-500',
    bgColor: 'bg-pink-500/10',
    borderColor: 'border-pink-500/30'
  },
];

export function Features() {
  return (
    <section id="features" className="py-24 bg-slate-900">
      <div className="container mx-auto px-6">
        <div className="text-center mb-16">
          <span className="inline-block px-4 py-1 rounded-full bg-indigo-500/20 border border-indigo-500/30 text-indigo-300 text-sm font-medium mb-4">
            核心功能
          </span>
          <h2 className="text-4xl md:text-5xl font-bold text-white mb-6">
            全方位智能运维能力
          </h2>
          <p className="text-xl text-gray-400 max-w-2xl mx-auto">
            从异常检测到自动修复，构建完整的智能运维闭环
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {features.map((feature) => {
            const Icon = feature.icon;
            return (
              <div
                key={feature.title}
                className={`group relative p-6 rounded-2xl ${feature.bgColor} border ${feature.borderColor} hover:border-opacity-60 transition-all duration-300 hover:scale-105 hover:shadow-xl`}
              >
                <div className={`inline-flex items-center justify-center w-12 h-12 rounded-xl bg-gradient-to-br ${feature.color} mb-4`}>
                  <Icon className="w-6 h-6 text-white" />
                </div>
                <h3 className="text-lg font-semibold text-white mb-2 group-hover:text-indigo-300 transition-colors">
                  {feature.title}
                </h3>
                <p className="text-gray-400 text-sm leading-relaxed">
                  {feature.description}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
