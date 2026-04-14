from django.db import models
from cmdb.models import Server


class Script(models.Model):
    """脚本库主表 (存储当前最新版本)"""
    TYPE_CHOICES = (
        ('sh', 'Shell Script'),
        ('py', 'Python'),
        ('yml', 'Ansible Playbook')
    )

    name = models.CharField("脚本名称", max_length=100)
    script_type = models.CharField("类型", max_length=10, choices=TYPE_CHOICES, default='sh')
    content = models.TextField("脚本内容")
    description = models.CharField("描述", max_length=200, blank=True)

    # 危险动作标记（预留字段，未来可用于执行时的二次确认）
    is_dangerous = models.BooleanField("高危脚本", default=False)

    # 审计信息
    created_by = models.CharField("创建人", max_length=50, default='system')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "脚本库"
        verbose_name_plural = "脚本库"
        ordering = ['-updated_at']


class ScriptHistory(models.Model):
    """脚本历史版本 (用于回滚和Diff)"""
    script = models.ForeignKey(Script, on_delete=models.CASCADE, related_name='history')
    version = models.IntegerField("版本号")
    content = models.TextField("历史内容")

    created_by = models.CharField("修改人", max_length=50)
    created_at = models.DateTimeField("修改时间", auto_now_add=True)
    memo = models.CharField("变更备注", max_length=200, blank=True)

    class Meta:
        verbose_name = "脚本历史"
        verbose_name_plural = "脚本历史"
        ordering = ['-version']  # 倒序排列，最新的在前面




class TaskExecution(models.Model):
    """批量执行任务记录"""
    script = models.ForeignKey(Script, on_delete=models.SET_NULL, null=True)
    user = models.CharField("执行人", max_length=50)

    # 执行配置
    target_servers = models.ManyToManyField(Server, verbose_name="目标主机")
    params = models.JSONField("执行参数", default=dict, blank=True)  # 存 {{ port }}: 8080
    concurrency = models.IntegerField("并发数", default=5)
    timeout = models.IntegerField("单机超时(秒)", default=60)
    # 状态
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    total_count = models.IntegerField(default=0)
    success_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    is_finished = models.BooleanField(default=False)

    class Meta:
        ordering = ['-start_time']


class TaskLog(models.Model):
    """单机执行日志"""
    execution = models.ForeignKey(TaskExecution, on_delete=models.CASCADE, related_name='logs')
    server = models.ForeignKey(Server, on_delete=models.CASCADE)

    status = models.CharField("状态", max_length=20, default='Pending')  # Pending, Running, Success, Failed
    stdout = models.TextField("标准输出", blank=True)
    stderr = models.TextField("错误输出", blank=True)
    exit_code = models.IntegerField("退出码", null=True)

    start_time = models.DateTimeField(null=True)
    end_time = models.DateTimeField(null=True)