import { Code, Database, Server, Cpu, Globe, GitBranch, Layers, Workflow } from 'lucide-react';

const techCategories = [
  {
    category: '后端框架',
    technologies: [
      { name: 'Django', icon: Globe, color: 'from-green-500 to-emerald-500' },
      { name: 'Django Channels', icon: Server, color: 'from-blue-500 to-cyan-500' },
      { name: 'Celery', icon: Workflow, color: 'from-orange-500 to-amber-500' },
    ]
  },
  {
    category: 'AI 引擎',
    technologies: [
      { name: 'Qwen3', icon: Cpu, color: 'from-purple-500 to-pink-500' },
      { name: 'OpenAI SDK', icon: Layers, color: 'from-indigo-500 to-blue-500' },
      { name: 'scikit-learn', icon: Code, color: 'from-yellow-500 to-orange-500' },
    ]
  },
  {
    category: '数据存储',
    technologies: [
      { name: 'PostgreSQL', icon: Database, color: 'from-blue-500 to-indigo-500' },
      { name: 'Redis', icon: Server, color: 'from-red-500 to-orange-500' },
      { name: 'SQLite', icon: Database, color: 'from-green-500 to-lime-500' },
    ]
  },
  {
    category: '运维工具',
    technologies: [
      { name: 'Kubernetes', icon: GitBranch, color: 'from-blue-500 to-cyan-500' },
      { name: 'Docker', icon: Server, color: 'from-blue-500 to-indigo-500' },
      { name: 'Prometheus', icon: Layers, color: 'from-orange-500 to-red-500' },
    ]
  },
];

export function TechStack() {
  return (
    <section id="tech-stack" className="py-24 bg-gradient-to-b from-slate-900 to-slate-800">
      <div className="container mx-auto px-6">
        <div className="text-center mb-16">
          <span className="inline-block px-4 py-1 rounded-full bg-indigo-500/20 border border-indigo-500/30 text-indigo-300 text-sm font-medium mb-4">
            技术栈
          </span>
          <h2 className="text-4xl md:text-5xl font-bold text-white mb-6">
            现代化技术架构
          </h2>
          <p className="text-xl text-gray-400 max-w-2xl mx-auto">
            采用业界领先的技术栈，构建稳定可靠的智能运维平台
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
          {techCategories.map((category) => (
            <div key={category.category} className="space-y-4">
              <h3 className="text-lg font-semibold text-indigo-400 mb-4">
                {category.category}
              </h3>
              <div className="space-y-3">
                {category.technologies.map((tech) => {
                  const Icon = tech.icon;
                  return (
                    <div
                      key={tech.name}
                      className="flex items-center gap-3 p-3 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 transition-all duration-300 hover:scale-[1.02]"
                    >
                      <div className={`inline-flex items-center justify-center w-10 h-10 rounded-lg bg-gradient-to-br ${tech.color}`}>
                        <Icon className="w-5 h-5 text-white" />
                      </div>
                      <span className="text-white font-medium">{tech.name}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
