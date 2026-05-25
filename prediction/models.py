import json
from django.db import models
from django.conf import settings
from django.utils import timezone

from cmdb.models import Server
from monitoring.models import AlertRule


class CapacityForecast(models.Model):
    METRIC_TYPE_CHOICES = [
        ('cpu', 'CPU使用率'),
        ('memory', '内存使用率'),
        ('disk', '磁盘使用率'),
    ]
    
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name='capacity_forecasts', verbose_name="服务器")
    metric_type = models.CharField("指标类型", max_length=20, choices=METRIC_TYPE_CHOICES)
    forecast_data = models.JSONField("预测值数组", default=list)
    forecast_date = models.DateField("预测日期", db_index=True)
    confidence = models.FloatField("置信度", default=0.0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = '容量预测结果'
        verbose_name_plural = '容量预测结果'
        unique_together = ('server', 'metric_type', 'forecast_date')
        indexes = [
            models.Index(fields=['server', 'metric_type', '-forecast_date']),
        ]
    
    def __str__(self):
        return f"{self.server.hostname} {self.get_metric_type_display()} @{self.forecast_date}"


class AlertForecast(models.Model):
    rule = models.ForeignKey(AlertRule, on_delete=models.CASCADE, related_name='alert_forecasts', verbose_name="告警规则")
    predicted_count = models.IntegerField("预测触发次数", default=0)
    predicted_time = models.DateTimeField("预测时间", db_index=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = '告警预测'
        verbose_name_plural = '告警预测'
        indexes = [
            models.Index(fields=['rule', '-predicted_time']),
        ]
    
    def __str__(self):
        return f"{self.rule.name}: {self.predicted_count}次 @{self.predicted_time}"


class AnomalyDetection(models.Model):
    SEVERITY_CHOICES = [
        ('high', '高度异常'),
        ('medium', '中度异常'),
        ('low', '轻度异常'),
    ]
    
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name='anomaly_detections', verbose_name="服务器", null=True, blank=True)
    detected_at = models.DateTimeField("检测时间", db_index=True)
    score = models.FloatField("异常分数")
    features = models.JSONField("参与计算的特征", default=dict)
    metric_name = models.CharField("指标名", max_length=50, default='')
    severity = models.CharField("异常程度", max_length=10, choices=SEVERITY_CHOICES, default='medium')
    method_used = models.CharField("使用方法", max_length=50, default='')
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = '异常检测结果'
        verbose_name_plural = '异常检测结果'
        ordering = ['-detected_at']
        indexes = [
            models.Index(fields=['server', '-detected_at']),
            models.Index(fields=['severity']),
        ]
    
    def __str__(self):
        server_name = self.server.hostname if self.server else 'N/A'
        return f"{server_name} {self.metric_name} score={self.score:.3f}"


class BaselineModel(models.Model):
    METRIC_TYPE_CHOICES = [
        ('cpu_usage', 'CPU使用率'),
        ('mem_usage', '内存使用率'),
        ('disk_usage', '磁盘使用率'),
        ('load_1min', '1分钟负载'),
        ('net_in', '入站流量'),
        ('net_out', '出站流量'),
    ]
    
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name='baseline_models', verbose_name="服务器")
    metric_type = models.CharField("指标类型", max_length=50, choices=METRIC_TYPE_CHOICES)
    baseline_data = models.JSONField("基线数据", default=dict)
    learned_periods = models.JSONField("学习到的周期", default=dict)
    
    last_learned_at = models.DateTimeField("最后学习时间", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = '智能基线'
        verbose_name_plural = '智能基线'
        unique_together = ('server', 'metric_type')
        indexes = [
            models.Index(fields=['server', 'metric_type']),
        ]
    
    def __str__(self):
        return f"{self.server.hostname} {self.metric_type}"