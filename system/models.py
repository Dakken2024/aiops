from django.db import models
from django.contrib.auth.models import AbstractUser
from django.urls import reverse
import json


class Tenant(models.Model):
    PLAN_CHOICES = [
        ('free', '免费版'),
        ('pro', '专业版'),
        ('enterprise', '企业版'),
    ]
    name = models.CharField("租户名称", max_length=100)
    plan = models.CharField("套餐", max_length=20, choices=PLAN_CHOICES, default='free')
    domain = models.CharField("域名", max_length=100, blank=True, null=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "租户"
        verbose_name_plural = "租户"

    def __str__(self):
        return self.name


class User(AbstractUser):
    phone = models.CharField("手机号", max_length=11, blank=True, null=True)
    department = models.CharField("部门", max_length=50, blank=True, null=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True, verbose_name="所属租户")

    class Meta:
        verbose_name = "用户"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.username


class SystemConfig(models.Model):
    """系统配置表 (Key-Value)"""
    key = models.CharField("配置项键", max_length=50, unique=True)
    value = models.TextField("配置项值", blank=True, null=True)
    description = models.CharField("描述", max_length=100, blank=True, null=True)

    class Meta:
        verbose_name = "系统配置"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.key} = {self.value}"


class Plugin(models.Model):
    """插件模型"""
    PLUGIN_TYPE_CHOICES = [
        ("collector", "采集插件"),
        ("notifier", "通知插件"),
        ("analyzer", "分析插件"),
        ("reporter", "报告插件"),
    ]

    name = models.CharField("插件名称", max_length=100, unique=True)
    type = models.CharField("插件类型", max_length=20, choices=PLUGIN_TYPE_CHOICES)
    path = models.CharField("插件路径", max_length=200, help_text="Python 模块路径，例如: plugins.example_collector")
    is_enabled = models.BooleanField("是否启用", default=False)
    config = models.JSONField("插件配置", default=dict, blank=True, null=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "插件"
        verbose_name_plural = verbose_name
        ordering = ["type", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"

    def get_config(self):
        """获取配置，兼容旧格式"""
        if isinstance(self.config, str):
            try:
                return json.loads(self.config)
            except (json.JSONDecodeError, TypeError):
                return {}
        return self.config or {}


class WebhookEndpoint(models.Model):
    METHOD_CHOICES = [
        ('POST', 'POST'),
        ('GET', 'GET'),
        ('PUT', 'PUT'),
    ]

    name = models.CharField("Webhook名称", max_length=200)
    url = models.URLField("目标URL")
    method = models.CharField("请求方法", max_length=10, choices=METHOD_CHOICES, default='POST')
    headers = models.JSONField("自定义请求头", default=dict, blank=True)
    secret = models.CharField("签名密钥", max_length=255, blank=True, default='',
                              help_text="用于HMAC签名，为空则不签名")
    enabled = models.BooleanField("是否启用", default=True)
    events = models.JSONField("订阅事件类型", default=list,
                              help_text="订阅的事件类型: ['alert_triggered', 'report_generated', 'anomaly_detected']")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)
    last_status = models.CharField("最后状态", max_length=50, blank=True, default='')
    last_sent_at = models.DateTimeField("最后发送时间", null=True, blank=True)

    class Meta:
        verbose_name = "Webhook端点"
        verbose_name_plural = "Webhook端点"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} -> {self.url}"

    def get_absolute_url(self):
        return reverse('webhook-endpoint-detail', args=[str(self.id)])


class WebhookLog(models.Model):
    STATUS_CHOICES = [
        ('pending', '待发送'),
        ('success', '成功'),
        ('failed', '失败'),
        ('retrying', '重试中'),
    ]

    endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE, related_name='logs', verbose_name="关联端点")
    event_type = models.CharField("事件类型", max_length=50)
    payload = models.JSONField("发送的数据")
    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default='pending')
    response_status = models.IntegerField("响应状态码", null=True, blank=True)
    response_body = models.TextField("响应内容", blank=True)
    error_message = models.TextField("错误信息", blank=True)
    retry_count = models.IntegerField("重试次数", default=0)
    max_retries = models.IntegerField("最大重试次数", default=3)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    sent_at = models.DateTimeField("发送时间", null=True, blank=True)

    class Meta:
        verbose_name = "Webhook日志"
        verbose_name_plural = "Webhook日志"
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.status}] {self.event_type} @ {self.endpoint.name}"