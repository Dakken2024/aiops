import { useState } from 'react';
import { Copy, Check, Terminal, FolderOpen, Settings, Database, Server } from 'lucide-react';

const steps = [
  {
    icon: FolderOpen,
    title: '克隆仓库',
    code: 'git clone <your-repo-url>\ncd aiops',
    description: '将项目代码克隆到本地'
  },
  {
    icon: Terminal,
    title: '安装依赖',
    code: 'conda create -n aiops python=3.12 -y\nconda activate aiops\npip install -r requirements.txt',
    description: '创建虚拟环境并安装依赖包'
  },
  {
    icon: Settings,
    title: '配置环境',
    code: 'cp .env.example .env\n# 编辑 .env 配置文件',
    description: '复制环境配置并填写必要参数'
  },
  {
    icon: Database,
    title: '初始化数据库',
    code: 'python reset_db.py\npython manage.py createsuperuser',
    description: '初始化数据库并创建管理员账号'
  },
  {
    icon: Server,
    title: '启动服务',
    code: 'daphne -b 0.0.0.0 -p 8000 ops_platform.asgi:application\ncelery -A ops_platform worker -l info -P eventlet',
    description: '启动 Web 服务和 Celery 异步任务'
  },
];

export function QuickStart() {
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);

  const copyToClipboard = (code: string, index: number) => {
    navigator.clipboard.writeText(code);
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  return (
    <section id="quick-start" className="py-24 bg-slate-900">
      <div className="container mx-auto px-6">
        <div className="text-center mb-16">
          <span className="inline-block px-4 py-1 rounded-full bg-indigo-500/20 border border-indigo-500/30 text-indigo-300 text-sm font-medium mb-4">
            快速开始
          </span>
          <h2 className="text-4xl md:text-5xl font-bold text-white mb-6">
            5 分钟快速部署
          </h2>
          <p className="text-xl text-gray-400 max-w-2xl mx-auto">
            简单几步即可启动 AiOps 智能运维平台
          </p>
        </div>

        <div className="max-w-4xl mx-auto">
          <div className="space-y-6">
            {steps.map((step, index) => {
              const Icon = step.icon;
              return (
                <div
                  key={index}
                  className="relative"
                >
                  <div className="flex gap-4 p-6 rounded-2xl bg-gradient-to-r from-slate-800/50 to-slate-900/50 border border-white/10 hover:border-indigo-500/30 transition-all duration-300">
                    <div className="flex-shrink-0">
                      <div className="flex items-center justify-center w-14 h-14 rounded-xl bg-gradient-to-br from-indigo-600 to-purple-600">
                        <Icon className="w-7 h-7 text-white" />
                      </div>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between mb-3">
                        <h3 className="text-xl font-semibold text-white">
                          <span className="text-indigo-400 mr-2">{index + 1}.</span>
                          {step.title}
                        </h3>
                        <button
                          onClick={() => copyToClipboard(step.code, index)}
                          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-gray-300 text-sm transition-colors"
                        >
                          {copiedIndex === index ? (
                            <>
                              <Check className="w-4 h-4 text-green-400" />
                              <span className="text-green-400">已复制</span>
                            </>
                          ) : (
                            <>
                              <Copy className="w-4 h-4" />
                              <span>复制</span>
                            </>
                          )}
                        </button>
                      </div>
                      <p className="text-gray-400 text-sm mb-3">{step.description}</p>
                      <pre className="bg-slate-950 rounded-lg p-4 overflow-x-auto">
                        <code className="text-sm text-gray-300 font-mono">{step.code}</code>
                      </pre>
                    </div>
                  </div>
                  {index < steps.length - 1 && (
                    <div className="absolute left-[3.5rem] top-full w-0.5 h-6 bg-gradient-to-b from-indigo-500/50 to-transparent" />
                  )}
                </div>
              );
            })}
          </div>

          <div className="mt-12 p-6 rounded-2xl bg-gradient-to-r from-indigo-600/20 to-purple-600/20 border border-indigo-500/30">
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-indigo-500/20 flex items-center justify-center">
                <Settings className="w-5 h-5 text-indigo-400" />
              </div>
              <div>
                <h4 className="text-lg font-semibold text-white mb-2">关键配置说明</h4>
                <p className="text-gray-300 text-sm">
                  在 <code className="px-2 py-0.5 bg-white/10 rounded text-indigo-300">.env</code> 文件中配置以下关键参数：
                </p>
                <ul className="mt-2 space-y-1 text-gray-400">
                  <li>• <span className="text-indigo-300">DJANGO_SECRET_KEY</span>: Django 密钥</li>
                  <li>• <span className="text-indigo-300">REDIS_*</span>: Redis 连接配置</li>
                  <li>• <span className="text-indigo-300">QWEN_API_KEY</span>: AI 诊断引擎密钥</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
