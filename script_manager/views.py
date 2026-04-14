from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from .models import Script, ScriptHistory, TaskExecution, TaskLog
from cmdb.models import ServerGroup, Server
from .tasks import execute_script_task
import json
import re
from ai_ops.models import AIModel
from ai_ops.utils import ask_ai
@login_required
def script_list(request):
    """脚本列表页"""
    scripts = Script.objects.all().order_by('-updated_at')
    return render(request, 'script_manager/script_list.html', {'scripts': scripts})


@login_required
def script_edit(request, script_id=None):
    """脚本编辑器页面"""
    script = None
    if script_id:
        script = get_object_or_404(Script, id=script_id)
    ai_models = AIModel.objects.all()
    return render(request, 'script_manager/script_edit.html', {
        'script': script,
        'ai_models': ai_models  # 传递模型列表
    })


@login_required
@csrf_exempt
def script_api(request):
    """脚本增删改查 API"""
    if request.method != 'POST': return JsonResponse({'status': False})
    action = request.POST.get('action')
    script_id = request.POST.get('script_id')

    try:
        if action == 'save':
            name = request.POST.get('name')
            stype = request.POST.get('type')
            content = request.POST.get('content')
            memo = request.POST.get('memo', 'Update')

            if script_id:
                script = Script.objects.get(id=script_id)
                if script.content != content:
                    last = script.history.first()
                    ver = (last.version + 1) if last else 1
                    ScriptHistory.objects.create(script=script, version=ver, content=script.content,
                                                 created_by=request.user.username, memo=memo)
                script.content = content
                script.name = name
                script.script_type = stype
                script.save()
            else:
                script = Script.objects.create(name=name, script_type=stype, content=content,
                                               created_by=request.user.username, description=memo)
                ScriptHistory.objects.create(script=script, version=1, content=content,
                                             created_by=request.user.username, memo="Initial")
            return JsonResponse({'status': True, 'msg': '保存成功', 'script_id': script.id})

        elif action == 'history_list':
            hists = ScriptHistory.objects.filter(script_id=script_id).values('id', 'version', 'created_at',
                                                                             'created_by', 'memo')
            return JsonResponse({'status': True, 'data': list(hists)})

        elif action == 'get_history':
            h = ScriptHistory.objects.get(id=request.POST.get('history_id'))
            return JsonResponse({'status': True, 'content': h.content})

        elif action == 'delete':
            Script.objects.filter(id=script_id).delete()
            return JsonResponse({'status': True, 'msg': '已删除'})

    except Exception as e:
        return JsonResponse({'status': False, 'msg': str(e)})
    return JsonResponse({'status': False})


# === 任务执行相关 ===

@login_required
def task_create(request, script_id):
    """执行向导"""
    script = get_object_or_404(Script, id=script_id)
    groups = ServerGroup.objects.all()
    var_pattern = re.compile(r'\{\{\s*(\w+)\s*\}\}')
    variables = list(set(var_pattern.findall(script.content)))
    return render(request, 'script_manager/task_create.html',
                  {'script': script, 'groups': groups, 'variables': variables})


@login_required
@csrf_exempt
def task_submit_api(request):
    """[关键修复] 提交任务 API"""
    if request.method != 'POST': return JsonResponse({'status': False})

    try:
        data = json.loads(request.body)
        script_id = data.get('script_id')
        server_ids = data.get('server_ids', [])
        params = data.get('params', {})
        concurrency = int(data.get('concurrency', 5))
        timeout = int(data.get('timeout', 60))

        if not server_ids:
            return JsonResponse({'status': False, 'msg': '请至少选择一台主机'})

        script = Script.objects.get(id=script_id)

        # 1. 创建主任务 (注意这里直接写入 total_count)
        task = TaskExecution.objects.create(
            script=script,
            user=request.user.username,
            params=params,
            concurrency=concurrency,
            timeout=timeout,
            total_count=len(server_ids)  # <--- 必须设置，否则前端显示 0
        )

        target_servers = Server.objects.filter(id__in=server_ids)
        task.target_servers.set(target_servers)

        # 2. [关键] 立即创建子任务日志 (状态 Pending)
        # 这样即使 Celery 没跑，页面上也能看到列表
        logs = []
        for s in target_servers:
            logs.append(TaskLog(execution=task, server=s, status='Pending'))
        TaskLog.objects.bulk_create(logs)

        # 3. 发送给 Celery
        execute_script_task.delay(task.id)

        return JsonResponse({'status': True, 'task_id': task.id})
    except Exception as e:
        return JsonResponse({'status': False, 'msg': str(e)})


@login_required
def task_detail(request, task_id):
    """
    任务详情页 (双重保险版)
    """
    task = get_object_or_404(TaskExecution, id=task_id)

    # [新增] 直接获取日志对象，传给模板渲染初始状态
    # 这样即使 AJAX 还没跑，页面上也会有数据
    initial_logs = task.logs.select_related('server').all().order_by('id')

    return render(request, 'script_manager/task_detail.html', {
        'task': task,
        'initial_logs': initial_logs  # 传递给模板
    })

@login_required
def task_result_api(request):
    """结果轮询接口"""
    task_id = request.GET.get('task_id')
    task = get_object_or_404(TaskExecution, id=task_id)

    # 获取日志列表
    logs = list(task.logs.values('server__hostname', 'server__ip_address', 'status', 'exit_code', 'id'))

    return JsonResponse({
        'status': True,
        'is_finished': task.is_finished,
        'summary': {
            'total': task.total_count,
            'success': task.success_count,
            'failed': task.failed_count,
            'waiting': task.total_count - task.success_count - task.failed_count
        },
        'logs': logs
    })


@login_required
@csrf_exempt
def task_log_content(request):
    """获取详细日志"""
    log_id = request.POST.get('log_id')
    log = TaskLog.objects.get(id=log_id)
    return JsonResponse({'status': True, 'stdout': log.stdout, 'stderr': log.stderr})


@login_required
@csrf_exempt
def script_ai_api(request):
    """
    脚本编辑器 AI 助手接口
    支持：生成(generate)、解释(explain)、审计(check)、优化(optimize)
    """
    if request.method != 'POST':
        return JsonResponse({'status': False, 'msg': 'Method not allowed'})

    action = request.POST.get('action')
    content = request.POST.get('content')
    script_type = request.POST.get('type', 'sh')
    model_id = request.POST.get('model_id')  # [关键] 获取前端传来的模型ID

    if not content:
        return JsonResponse({'status': False, 'msg': '内容不能为空'})

    lang_map = {'sh': 'Shell (Bash)', 'py': 'Python 3', 'yml': 'Ansible Playbook'}
    lang = lang_map.get(script_type, 'Shell')

    # 1. 生成脚本
    if action == 'generate':
        prompt = f"""
        你是一个资深的 DevOps 工程师。请根据用户需求生成一段高质量的 {lang} 脚本。
        【用户需求】：{content}
        【要求】：
        1. 直接输出代码，不要包含 ``` 标记。
        2. 代码应当包含适当的中文注释。
        3. 考虑异常处理和安全性。
        """
        system_role = "Script Generator"

    # 2. 解释脚本
    elif action == 'explain':
        prompt = f"""
        请用通俗易懂的中文解释以下运维脚本的功能、流程和关键点：
        【脚本内容】：
        {content}
        请按结构回答：
        1. **功能摘要**
        2. **执行流程**
        3. **注意事项**
        """
        system_role = "Code Explainer"

    # 3. 审计纠错
    elif action == 'check':
        prompt = f"""
        请作为安全审计专家，Review 以下 {lang} 脚本，查找潜在的语法错误、逻辑漏洞和安全风险。
        【脚本内容】：
        {content}
        【输出格式】：
        1. **综合评分** (0-100)
        2. **风险项**
        3. **优化建议**
        """
        system_role = "Security Auditor"

    # 4. [新增] 优化脚本
    elif action == 'optimize':
        prompt = f"""
        请作为一名资深开发专家，重构优化以下 {lang} 脚本。

        【脚本内容】：
        {content}

        【优化目标】：
        1. 提高执行效率和代码鲁棒性。
        2. 增强可读性（添加关键注释）。
        3. 遵循最佳实践（例如 Shell 脚本增加 set -e，变量加引号等）。
        4. 如果有潜在 bug，请一并修复。

        【输出要求】：
        1. 仅输出优化后的完整代码，不要包含 ``` 代码块标记，不要包含多余解释文字。
        2. 保持原有核心功能逻辑不变。
        """
        system_role = "Code Refactor Expert"

    else:
        return JsonResponse({'status': False, 'msg': '未知操作'})

    # 调用 AI
    try:
        result = ask_ai(prompt, model_id=model_id, system_role=system_role)
        if 'error' in result:
            return JsonResponse({'status': False, 'msg': result['error']})

        res_content = result['content']

        # [处理] 如果是生成或优化，需要清洗 Markdown 标记
        if action in ['generate', 'optimize']:
            res_content = res_content.replace('```python', '').replace('```bash', '').replace('```sh', '').replace(
                '```yaml', '').replace('```', '').strip()

        return JsonResponse({'status': True, 'data': res_content})

    except Exception as e:
        return JsonResponse({'status': False, 'msg': str(e)})

@login_required
def task_list(request):
    """
    执行历史列表页
    """
    # 获取最近的 50 条记录，按时间倒序
    tasks = TaskExecution.objects.select_related('script').all().order_by('-start_time')[:50]
    return render(request, 'script_manager/task_list.html', {'tasks': tasks})