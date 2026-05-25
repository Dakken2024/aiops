from django.db import models
from django.utils import timezone


class Trace(models.Model):
    trace_id = models.CharField("追踪ID", max_length=32, unique=True, db_index=True)
    name = models.CharField("服务名称", max_length=100, db_index=True)
    start_time = models.DateTimeField("开始时间", db_index=True)
    end_time = models.DateTimeField("结束时间", null=True, blank=True)
    duration_ms = models.FloatField("总耗时(ms)", default=0)
    tags = models.JSONField("标签", default=dict)

    class Meta:
        verbose_name = "追踪记录"
        verbose_name_plural = "追踪记录"
        ordering = ['-start_time']

    def __str__(self):
        return f"{self.name} - {self.trace_id[:8]}"


class Span(models.Model):
    STATUS_CHOICES = [
        ('ok', '正常'),
        ('error', '错误'),
    ]

    trace = models.ForeignKey(Trace, on_delete=models.CASCADE, related_name='spans', verbose_name="所属追踪")
    span_id = models.CharField("Span ID", max_length=16)
    parent_span_id = models.CharField("父Span ID", max_length=16, null=True, blank=True)
    name = models.CharField("操作名称", max_length=200)
    start_time = models.DateTimeField("开始时间", db_index=True)
    duration_ms = models.FloatField("耗时(ms)", default=0)
    status_code = models.CharField("状态码", max_length=10, choices=STATUS_CHOICES, default='ok', db_index=True)
    attributes = models.JSONField("属性", default=dict)

    class Meta:
        verbose_name = "Span记录"
        verbose_name_plural = "Span记录"
        ordering = ['start_time']
        indexes = [
            models.Index(fields=['trace', 'start_time']),
            models.Index(fields=['status_code', 'start_time']),
        ]

    def __str__(self):
        return f"{self.name} ({self.duration_ms}ms)"


class ServiceMap(models.Model):
    service_name = models.CharField("服务名称", max_length=100, db_index=True)
    target_service = models.CharField("目标服务", max_length=100, db_index=True)
    call_count = models.IntegerField("调用次数", default=0)
    avg_duration_ms = models.FloatField("平均耗时(ms)", default=0)
    last_seen = models.DateTimeField("最后调用时间", db_index=True)

    class Meta:
        verbose_name = "服务调用拓扑"
        verbose_name_plural = "服务调用拓扑"
        unique_together = ('service_name', 'target_service')

    def __str__(self):
        return f"{self.service_name} -> {self.target_service} (×{self.call_count})"
