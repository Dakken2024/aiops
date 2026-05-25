from django.db import models
from django.utils import timezone
from cmdb.models import Server
from system.models import Tenant
from system.managers import TenantManager


class LogSource(models.Model):
    TYPE_CHOICES = [
        ('syslog', 'Syslog'),
        ('file', '文件日志'),
        ('k8s', 'Kubernetes'),
        ('docker', 'Docker'),
    ]

    name = models.CharField("名称", max_length=100)
    type = models.CharField("类型", max_length=20, choices=TYPE_CHOICES)
    config = models.JSONField("配置", default=dict,
        help_text="路径、端口等配置信息")
    is_enabled = models.BooleanField("是否启用", default=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True, verbose_name="所属租户")
    
    objects = TenantManager()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '日志来源'
        verbose_name_plural = '日志来源'

    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"


class LogPattern(models.Model):
    SEVERITY_CHOICES = [
        ('debug', 'DEBUG'),
        ('info', 'INFO'),
        ('warning', 'WARNING'),
        ('error', 'ERROR'),
        ('critical', 'CRITICAL'),
    ]

    pattern = models.CharField("正则表达式", max_length=500)
    description = models.TextField("描述", blank=True)
    severity = models.CharField("严重级别", max_length=20, choices=SEVERITY_CHOICES, default='info')
    occurrences = models.IntegerField("出现次数", default=0)
    first_seen = models.DateTimeField("首次出现", auto_now_add=True)
    last_seen = models.DateTimeField("最后出现", auto_now=True)
    
    class Meta:
        verbose_name = '日志模式'
        verbose_name_plural = '日志模式'

    def __str__(self):
        return f"{self.pattern[:50]} ({self.occurrences}次)"


class LogEntry(models.Model):
    LEVEL_CHOICES = [
        ('debug', 'DEBUG'),
        ('info', 'INFO'),
        ('warning', 'WARNING'),
        ('error', 'ERROR'),
        ('critical', 'CRITICAL'),
    ]

    source = models.ForeignKey(LogSource, on_delete=models.CASCADE, related_name='log_analysis_entries', verbose_name="日志来源")
    server = models.ForeignKey(Server, on_delete=models.SET_NULL, null=True, blank=True, related_name='log_analysis_entries', verbose_name="服务器")
    timestamp = models.DateTimeField("日志时间", db_index=True)
    level = models.CharField("级别", max_length=20, choices=LEVEL_CHOICES, db_index=True)
    message = models.TextField("日志内容")
    parsed_data = models.JSONField("解析后数据", default=dict)
    pattern = models.ForeignKey(LogPattern, on_delete=models.SET_NULL, null=True, blank=True, related_name='log_analysis_entries', verbose_name="匹配模式")
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '日志条目'
        verbose_name_plural = '日志条目'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['source', '-timestamp']),
            models.Index(fields=['server', '-timestamp']),
            models.Index(fields=['level', '-timestamp']),
        ]

    def __str__(self):
        return f"[{self.level}] {self.message[:80]}"


class LogAlertRule(models.Model):
    TRIGGER_TYPE_CHOICES = [
        ('keyword', '关键字匹配'),
        ('pattern', '模式匹配'),
        ('level', '级别匹配'),
    ]

    name = models.CharField("规则名称", max_length=200)
    description = models.TextField("描述", blank=True)
    trigger_type = models.CharField("触发类型", max_length=20, choices=TRIGGER_TYPE_CHOICES)
    
    keywords = models.JSONField("关键字列表", default=list, help_text="关键字匹配模式下使用")
    pattern_id = models.ForeignKey(LogPattern, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="匹配模式")
    level_filter = models.CharField("级别过滤", max_length=50, blank=True, default='',
        help_text="逗号分隔的级别列表，例如：error,critical")
    
    threshold_count = models.IntegerField("触发阈值", default=1,
        help_text="在时间窗口内达到此数量触发告警")
    time_window_minutes = models.IntegerField("时间窗口(分钟)", default=5)
    
    is_enabled = models.BooleanField("是否启用", default=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True, verbose_name="所属租户")
    
    objects = TenantManager()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_triggered_at = models.DateTimeField("最后触发时间", null=True, blank=True)
    trigger_count = models.IntegerField("触发次数", default=0)

    class Meta:
        verbose_name = '日志告警规则'
        verbose_name_plural = '日志告警规则'

    def __str__(self):
        return self.name


class LogAlert(models.Model):
    STATUS_CHOICES = [
        ('firing', '触发中'),
        ('resolved', '已恢复'),
        ('acknowledged', '已确认'),
    ]

    rule = models.ForeignKey(LogAlertRule, on_delete=models.CASCADE, related_name='alerts', verbose_name="告警规则")
    server = models.ForeignKey(Server, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="服务器")
    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default='firing')
    message = models.TextField("告警消息")
    detail = models.JSONField("详细信息", default=dict)
    
    fired_at = models.DateTimeField("触发时间", auto_now_add=True)
    resolved_at = models.DateTimeField("恢复时间", null=True, blank=True)
    acknowledged_at = models.DateTimeField("确认时间", null=True, blank=True)
    
    class Meta:
        verbose_name = '日志告警'
        verbose_name_plural = '日志告警'
        ordering = ['-fired_at']

    def __str__(self):
        return f"[{self.status}] {self.rule.name}"