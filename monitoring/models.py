import json
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.postgres.indexes import GinIndex

try:
    from pgvector.django import VectorField
    HAS_PGVECTOR = True
except ImportError:
    HAS_PGVECTOR = False

def _vector_field(dimensions=1536, **kwargs):
    if HAS_PGVECTOR:
        return VectorField(dimensions=dimensions, null=True, blank=True, **kwargs)
    return models.TextField(null=True, blank=True, **kwargs)


class AlertRule(models.Model):
    SEVERITY_CHOICES = [
        ('P0', '致命 (Critical)'),
        ('P1', '严重 (Major)'),
        ('P2', '警告 (Warning)'),
        ('P3', '提示 (Info)'),
    ]
    STATUS_CHOICES = [
        ('enabled', '启用'),
        ('disabled', '禁用'),
        ('draft', '草稿'),
    ]
    RULE_TYPE_CHOICES = [
        ('threshold', '静态阈值'),
        ('baseline', '动态基线'),
        ('trend', '趋势检测'),
        ('composite', '复合条件'),
        ('absence', '消失检测'),
        ('anomaly', '异常检测'),
    ]

    name = models.CharField("规则名称", max_length=200, unique=True)
    description = models.TextField("规则描述", blank=True)
    rule_type = models.CharField("规则类型", max_length=20, choices=RULE_TYPE_CHOICES, default='threshold')
    severity = models.CharField("严重级别", max_length=10, choices=SEVERITY_CHOICES, default='P1')
    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default='enabled')

    target_all = models.BooleanField("应用于所有服务器", default=True)
    metric_name = models.CharField("监控指标", max_length=50, default='cpu_usage',
        help_text="cpu_usage / mem_usage / disk_usage / load_1min / net_in / net_out")
    condition_config = models.JSONField("条件配置", default=dict,
        help_text="静态阈值:{'operator':'gt','value':90} / 动态基线:{'multiplier':1.5}")

    evaluate_interval = models.PositiveIntegerField("评估间隔(秒)", default=60)
    lookback_window = models.PositiveIntegerField("回溯窗口(个)", default=5)
    cooldown_seconds = models.PositiveIntegerField("冷却时间(秒)", default=300,
        help_text="同一目标触发后N秒内不再重复触发")
    max_alerts_per_hour = models.PositiveIntegerField("每小时最大告警数", default=10)

    notify_channels = models.JSONField("通知渠道", default=list, help_text="['dingtalk','wechat','email']")
    notify_template = models.TextField("通知模板", blank=True, default="")

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_triggered_at = models.DateTimeField("最后触发时间", null=True, blank=True)
    trigger_count = models.PositiveIntegerField("累计触发次数", default=0)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "预警规则"
        verbose_name_plural = "预警规则"
        indexes = [
            models.Index(fields=['status', 'rule_type']),
            models.Index(fields=['severity']),
        ]

    def __str__(self):
        return f"[{self.severity}] {self.name}"


class AlertEvent(models.Model):
    STATUS_CHOICES = [
        ('firing', '触发中'), ('resolved', '已恢复'),
        ('acknowledged', '已确认'), ('silenced', '已静默'),
    ]

    RESOLVE_REASON_CHOICES = [
        ('auto_recovered', '自动恢复'),
        ('manual_fixed', '手动修复'),
        ('false_positive', '误报'),
        ('known_issue', '已知问题/暂不处理'),
        ('maintenance', '计划内维护'),
        ('ignored', '忽略/无需处理'),
        ('other', '其他原因'),
    ]

    rule = models.ForeignKey(AlertRule, on_delete=models.CASCADE, related_name='events')
    server = models.ForeignKey('cmdb.Server', on_delete=models.CASCADE, null=True, related_name='alert_events')

    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default='firing')
    severity = models.CharField("级别", max_length=10)
    metric_name = models.CharField("指标名", max_length=50)
    current_value = models.FloatField("当前值")
    threshold_value = models.FloatField("阈值/基线", null=True, blank=True)
    message = models.TextField("告警消息", default="")
    detail = models.JSONField("详细信息", default=dict)

    fired_at = models.DateTimeField("触发时间", auto_now_add=True)
    resolved_at = models.DateTimeField("恢复时间", null=True, blank=True)
    acknowledged_at = models.DateTimeField("确认时间", null=True, blank=True)
    acknowledged_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name='acknowledged_alerts')
    notification_log = models.JSONField("通知记录", default=list)

    resolve_reason = models.CharField("关闭原因", max_length=30, choices=RESOLVE_REASON_CHOICES,
                                     blank=True, null=True)
    resolve_comment = models.TextField("处理备注", blank=True, default='')
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='resolved_alerts')

    class Meta:
        ordering = ['-fired_at']
        verbose_name = "告警事件"
        indexes = [
            models.Index(fields=['status', '-fired_at']),
            models.Index(fields=['server', 'status']),
        ]

    @property
    def duration(self):
        end = self.resolved_at or timezone.now()
        return (end - self.fired_at).total_seconds()

    @property
    def comment_count(self):
        return self.comments.count()


class AlertComment(models.Model):
    COMMENT_TYPE_CHOICES = [
        ('text', '普通评论'),
        ('status_change', '状态变更'),
        ('resolve', '解决关闭'),
        ('escalate', '升级通知'),
        ('internal', '内部备注'),
    ]

    alert_event = models.ForeignKey(AlertEvent, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                               related_name='alert_comments')
    comment_type = models.CharField("评论类型", max_length=20, choices=COMMENT_TYPE_CHOICES, default='text')
    content = models.TextField("评论内容")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    is_internal = models.BooleanField("仅内部可见", default=False)

    class Meta:
        ordering = ['created_at']
        verbose_name = "告警评论"
        verbose_name_plural = "告警评论"

    def __str__(self):
        return f"[{self.get_comment_type_display()}] {self.content[:30]}"


class AlertSilenceRule(models.Model):
    name = models.CharField("静默名称", max_length=200)
    match_severity = models.CharField("匹配级别", max_length=10, blank=True, default='')
    match_rule_name = models.CharField("匹配规则", max_length=200, blank=True, default='')
    match_server = models.ForeignKey('cmdb.Server', on_delete=models.CASCADE, null=True, blank=True)
    start_time = models.DateTimeField("开始时间")
    end_time = models.DateTimeField("结束时间")
    comment = models.TextField("备注", blank=True)
    is_active = models.BooleanField("生效中", default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "静默规则"


class NotificationLog(models.Model):
    CHANNEL_CHOICES = [('dingtalk','钉钉'),('wechat','企业微信'),('email','邮件'),('slack','Slack'),('webhook','Webhook')]
    STATUS_CHOICES = [('sent','已发送'),('failed','发送失败'),('retrying','重试中')]

    alert_event = models.ForeignKey(AlertEvent, on_delete=models.CASCADE, related_name='notify_logs')
    channel = models.CharField("渠道", max_length=20, choices=CHANNEL_CHOICES)
    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES)
    recipient = models.JSONField("接收者信息", default=dict)
    content_summary = models.TextField("内容摘要", blank=True)
    error_message = models.TextField("错误信息", blank=True)
    retry_count = models.PositiveIntegerField("重试次数", default=0)
    sent_at = models.DateTimeField("发送时间", auto_now_add=True)

    class Meta:
        ordering = ['-sent_at']
        verbose_name = "通知记录"


class DetectorConfig(models.Model):
    DETECTOR_CHOICES = [
        ('zscore', 'Z-Score 检测器'),
        ('iqr', 'IQR 四分位距检测器'),
        ('moving_avg', '移动平均检测器'),
        ('rate_of_change', '变化率检测器'),
        ('composite', '复合投票检测器'),
    ]

    detector_name = models.CharField("检测器名称", max_length=20, choices=DETECTOR_CHOICES, unique=True)
    is_enabled = models.BooleanField("是否启用", default=True)
    params = models.JSONField("参数配置", default=dict,
        help_text="zscore:{threshold:2.5} / iqr:{k:1.5} / moving_avg:{window:10,factor:2.0} / rate_of_change:{threshold:0.5,window:5} / composite:{vote_thr:0.6}")
    description = models.TextField("说明", blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = "检测器配置"
        verbose_name_plural = "检测器配置"

    def __str__(self):
        return f"{self.get_detector_name_display()} ({'启用' if self.is_enabled else '禁用'})"

    def get_param(self, key, default=None):
        return self.params.get(key, default)


class AnomalyHistory(models.Model):
    SEVERITY_CHOICES = [
        ('high', '高度异常'),
        ('medium', '中度异常'),
        ('low', '轻度异常'),
    ]

    server = models.ForeignKey('cmdb.Server', on_delete=models.CASCADE, related_name='anomaly_histories',
                               verbose_name="服务器", null=True, blank=True)
    metric_name = models.CharField("指标名", max_length=50)

    detected_at = models.DateTimeField("检测时间", db_index=True)
    severity = models.CharField("异常程度", max_length=10, choices=SEVERITY_CHOICES, default='medium')

    anomaly_score = models.FloatField("异常分数", default=0.0)
    method_used = models.CharField("使用的检测方法", max_length=30)
    raw_values = models.JSONField("原始数据序列", default=list)

    current_value = models.FloatField("当前值")
    baseline_value = models.FloatField("基线值", null=True, blank=True)
    deviation_percent = models.FloatField("偏差百分比", null=True, blank=True)

    alert_event = models.OneToOneField(AlertEvent, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='anomaly_history', verbose_name="关联告警")

    ai_diagnosis = models.TextField("AI诊断结论", blank=True, default='')
    confidence = models.FloatField("AI置信度", default=0.0, null=True, blank=True)
    ai_confidence = models.FloatField("AI置信度", null=True, blank=True)
    ai_analyzed_at = models.DateTimeField("AI分析时间", null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "异常历史"
        verbose_name_plural = "异常历史"
        ordering = ['-detected_at']
        indexes = [
            models.Index(fields=['server', 'detected_at'], name='idx_anomaly_server_time'),
            models.Index(fields=['metric_name', 'detected_at'], name='idx_anomaly_metric_time'),
            models.Index(fields=['severity'], name='idx_anomaly_severity'),
        ]

    @property
    def duration_minutes(self):
        if self.alert_event and self.alert_event.resolved_at:
            delta = self.alert_event.resolved_at - self.detected_at
            return int(delta.total_seconds() / 60)
        return None


class AlertGroup(models.Model):
    name = models.CharField(max_length=255, verbose_name='聚合组名')
    fingerprint = models.CharField(max_length=64, unique=True, db_index=True, verbose_name='指纹')
    status = models.CharField(max_length=20, default='firing',
        choices=[('firing','触发中'),('resolved','已解决')], db_index=True)
    severity = models.CharField(max_length=10, default='P2')
    alert_count = models.IntegerField(default=0, verbose_name='告警总数')
    first_fired_at = models.DateTimeField(auto_now_add=True)
    last_fired_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ['-last_fired_at']
        verbose_name = '告警聚合组'
        verbose_name_plural = '告警聚合组'

    def __str__(self):
        return f"[{self.status}] {self.name} ({self.alert_count}次)"


class AlertCorrelationRule(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    trigger_patterns = models.JSONField(default=dict, verbose_name='触发条件组合')
    root_cause_hint = models.CharField(max_length=500, verbose_name='根因提示')
    suggested_action = models.TextField(blank=True, verbose_name='建议操作')
    confidence_weight = models.FloatField(default=0.8, verbose_name='置信度权重')
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = '告警关联规则'
        verbose_name_plural = '告警关联规则'

    def __str__(self):
        return self.name


class RemediationAction(models.Model):
    ACTION_CHOICES = [
        ('script', '执行脚本'),
        ('service_restart', '重启服务'),
        ('disk_cleanup', '磁盘清理'),
        ('scale_out', '扩容'),
        ('webhook', '调用Webhook'),
        ('custom', '自定义'),
    ]

    name = models.CharField(max_length=200, verbose_name='动作名称')
    action_type = models.CharField(max_length=50, choices=ACTION_CHOICES, default='script')
    target_command = models.TextField(verbose_name='目标命令/脚本')
    severity_filter = models.CharField(max_length=20, default='P1,P2',
        help_text='适用此动作的告警级别(逗号分隔)')
    timeout_seconds = models.IntegerField(default=300, verbose_name='超时秒数')
    max_retries = models.IntegerField(default=1, verbose_name='最大重试')
    is_dangerous = models.BooleanField(default=False, verbose_name='危险操作(需确认)')
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = '修复动作'
        verbose_name_plural = '修复动作'

    def __str__(self):
        return f"{self.name} ({self.get_action_type_display()})"

    def matches_severity(self, severity):
        return severity in [s.strip() for s in self.severity_filter.split(',')]


class RemediationHistory(models.Model):
    STATUS_CHOICES = [
        ('pending', '待执行'), ('running', '执行中'), ('success', '成功'),
        ('failed', '失败'), ('timeout', '超时'), ('cancelled', '已取消'),
    ]

    alert_event = models.ForeignKey(AlertEvent, on_delete=models.CASCADE)
    action = models.ForeignKey(RemediationAction, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, default='pending', choices=STATUS_CHOICES)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    output = models.TextField(blank=True, verbose_name='执行输出')
    error_message = models.TextField(blank=True)
    execution_mode = models.CharField("执行方式", max_length=20, default='ssh', blank=True)
    decision_mode = models.CharField("决策模式", max_length=20, default='auto_confirm', blank=True)

    class Meta:
        ordering = ['-started_at']
        verbose_name = '修复记录'
        verbose_name_plural = '修复记录'

    def __str__(self):
        return f"[{self.status}] {self.action.name} @ {self.started_at:%m-%d %H:%M}"


class RunbookEntry(models.Model):
    CATEGORY_CHOICES = [
        ('network', '网络'), ('storage', '存储'), ('memory', '内存'),
        ('cpu', '计算'), ('database', '数据库'), ('application', '应用'),
        ('security', '安全'), ('general', '通用'),
    ]

    title = models.CharField(max_length=300, verbose_name='标题')
    problem_pattern = models.JSONField(default=dict, verbose_name='问题特征模式')
    solution = models.TextField(verbose_name='解决方案')
    category = models.CharField(max_length=50, default='general', choices=CATEGORY_CHOICES)
    tags = models.CharField(max_length=300, blank=True, verbose_name='标签(逗号分隔)')
    effectiveness_score = models.FloatField(default=0.0, verbose_name='有效评分')
    usage_count = models.IntegerField(default=0, verbose_name='使用次数')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ['-effectiveness_score']
        verbose_name = '运维知识条目'
        verbose_name_plural = '运维知识条目'

    def __str__(self):
        return self.title

    @property
    def tag_list(self):
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(',')]


class AgentToken(models.Model):
    name = models.CharField(max_length=200, verbose_name='Agent 名称')
    token = models.CharField(max_length=64, unique=True, db_index=True,
        verbose_name='API Token')
    server = models.OneToOneField('cmdb.Server', on_delete=models.CASCADE,
        related_name='monitoring_agent_token', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Agent Token'
        verbose_name_plural = 'Agent Tokens'

    def __str__(self):
        return f"{self.name} ({self.server.hostname if self.server else '未绑定'})"


class EscalationPolicy(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    match_rules = models.JSONField(default=dict, verbose_name='匹配规则')
    escalation_steps = models.JSONField(default=list, verbose_name='升级步骤')
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = '升级策略'
        verbose_name_plural = '升级策略'

    def __str__(self):
        return self.name


class ServiceTopology(models.Model):
    SERVICE_TYPE_CHOICES = [
        ('application', '应用服务'), ('database', '数据库'),
        ('cache', '缓存'), ('queue', '消息队列'),
        ('lb', '负载均衡'), ('storage', '存储'), ('external', '外部服务'),
    ]

    name = models.CharField(max_length=200, verbose_name='服务名')
    service_type = models.CharField(max_length=50, default='application',
        choices=SERVICE_TYPE_CHOICES)
    server = models.ForeignKey('cmdb.Server', on_delete=models.CASCADE,
        null=True, blank=True, related_name='topology_nodes')
    health_endpoint = models.URLField(blank=True, verbose_name='健康检查URL')
    depends_on = models.ManyToManyField('self', symmetrical=False, blank=True,
        related_name='dependents', verbose_name='依赖的服务')

    class Meta:
        verbose_name = '服务拓扑节点'
        verbose_name_plural = '服务拓扑节点'

    def __str__(self):
        return f"[{self.get_service_type_display()}] {self.name}"


class SavedDashboard(models.Model):
    name = models.CharField(max_length=200)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    config = models.JSONField(verbose_name='面板配置(图表类型/指标/布局)')
    is_public = models.BooleanField(default=False, verbose_name='是否公开')
    share_token = models.CharField(max_length=32, unique=True, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = '已保存的仪表盘'
        verbose_name_plural = '已保存的仪表盘'

    def __str__(self):
        return self.name


class HealthScore(models.Model):
    GRADE_CHOICES = [
        ('A', '优秀(A)'), ('B', '良好(B)'), ('C', '一般(C)'),
        ('D', '警告(D)'), ('F', '严重(F)'),
    ]

    server = models.ForeignKey('cmdb.Server', on_delete=models.CASCADE, related_name='health_scores')
    scored_at = models.DateTimeField(db_index=True)
    overall_score = models.FloatField(default=0.0, verbose_name='综合评分(0-100)')

    cpu_score = models.FloatField(default=100)
    mem_score = models.FloatField(default=100)
    disk_score = models.FloatField(default=100)
    network_score = models.FloatField(default=100)
    availability_score = models.FloatField(default=100)

    alert_penalty = models.FloatField(default=0, verbose_name='告警扣分')
    anomaly_penalty = models.FloatField(default=0, verbose_name='异常扣分')

    grade = models.CharField(max_length=10, default='A', choices=GRADE_CHOICES)

    class Meta:
        ordering = ['-scored_at']
        verbose_name = '健康评分'
        verbose_name_plural = '健康评分'
        indexes = [
            models.Index(fields=['server', '-scored_at']),
        ]

    def __str__(self):
        return f"{self.server.hostname}: {self.overall_score:.1f} ({self.grade})"


class CloudResource(models.Model):
    PROVIDER_CHOICES = [
        ('aliyun', '阿里云'), ('tencent', '腾讯云'),
        ('huawei', '华为云'), ('aws', 'AWS'),
    ]
    RESOURCE_TYPE_CHOICES = [
        ('ecs', '云服务器'), ('rds', '云数据库'),
        ('slb', '负载均衡'), ('oss', '对象存储'),
        ('redis_cloud', '云缓存'), ('cdn', 'CDN'),
    ]
    provider = models.CharField("云厂商", max_length=20, choices=PROVIDER_CHOICES)
    resource_type = models.CharField("资源类型", max_length=20, choices=RESOURCE_TYPE_CHOICES)
    instance_id = models.CharField("实例ID", max_length=100)
    instance_name = models.CharField("实例名称", max_length=200, default='')
    region = models.CharField("区域", max_length=50, default='')
    cloud_account = models.ForeignKey('cmdb.CloudAccount', on_delete=models.CASCADE,
        related_name='cloud_resources', verbose_name="云账号")
    local_server = models.ForeignKey('cmdb.Server', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cloud_resource', verbose_name="关联本地服务器")
    extra_config = models.JSONField("扩展配置", default=dict)
    last_sync_at = models.DateTimeField("最后同步时间", null=True, blank=True)
    is_active = models.BooleanField("是否启用", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '云资源'
        verbose_name_plural = '云资源'
        unique_together = ('cloud_account', 'instance_id')
        indexes = [
            models.Index(fields=['provider', 'resource_type']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"[{self.get_provider_display()}] {self.instance_name or self.instance_id}"


class DataRetentionPolicy(models.Model):
    INTERVAL_CHOICES = [
        ('5m', '5分钟'), ('1h', '1小时'), ('1d', '1天'),
    ]
    name = models.CharField("策略名称", max_length=100)
    metric_type = models.CharField("指标类型", max_length=50, default='raw',
        help_text="raw=原始明细, aggregated=聚合数据")
    retention_days = models.PositiveIntegerField("保留天数", default=30)
    aggregation_interval = models.CharField("聚合间隔", max_length=20, default='1h',
        choices=INTERVAL_CHOICES)
    is_active = models.BooleanField("是否启用", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '数据保留策略'
        verbose_name_plural = '数据保留策略'

    def __str__(self):
        return f"{self.name} ({self.metric_type}: {self.retention_days}天)"


class MetricAggregation(models.Model):
    INTERVAL_CHOICES = [
        ('5m', '5分钟'), ('1h', '1小时'), ('1d', '1天'),
    ]
    server = models.ForeignKey('cmdb.Server', on_delete=models.CASCADE,
        null=True, blank=True, related_name='metric_aggregations', verbose_name="服务器")
    cloud_resource = models.ForeignKey(CloudResource, on_delete=models.CASCADE,
        null=True, blank=True, related_name='metric_aggregations', verbose_name="云资源")
    metric_type = models.CharField("指标类型", max_length=50,
        help_text="cpu_usage/mem_usage/disk_usage等")
    aggregation_interval = models.CharField("聚合间隔", max_length=20, default='1h',
        choices=INTERVAL_CHOICES)
    avg_value = models.FloatField("平均值", default=0.0)
    max_value = models.FloatField("最大值", default=0.0)
    min_value = models.FloatField("最小值", default=0.0)
    sample_count = models.PositiveIntegerField("样本数", default=0)
    timestamp = models.DateTimeField("时间戳", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '指标聚合'
        verbose_name_plural = '指标聚合'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['server', 'metric_type', '-timestamp']),
            models.Index(fields=['cloud_resource', 'metric_type', '-timestamp']),
        ]

    def __str__(self):
        target = self.server.hostname if self.server else (self.cloud_resource.instance_name if self.cloud_resource else '?')
        return f"{target} {self.metric_type} avg={self.avg_value:.1f} @{self.timestamp:%m-%d %H:%M}"


class LogEntry(models.Model):
    LEVEL_CHOICES = [
        ('EMERG', 'EMERG'), ('ALERT', 'ALERT'), ('CRIT', 'CRIT'),
        ('ERROR', 'ERROR'), ('WARN', 'WARN'), ('NOTICE', 'NOTICE'),
        ('INFO', 'INFO'), ('DEBUG', 'DEBUG'),
    ]
    server = models.ForeignKey('cmdb.Server', on_delete=models.CASCADE,
        related_name='log_entries', verbose_name="服务器")
    timestamp = models.DateTimeField("日志时间", db_index=True)
    level = models.CharField("级别", max_length=10, choices=LEVEL_CHOICES, db_index=True)
    source = models.CharField("来源", max_length=50, default='syslog')
    message = models.TextField("日志内容")
    message_vector = _vector_field(dimensions=1536)
    structured_data = models.JSONField("结构化数据", default=dict)
    is_anomaly = models.BooleanField("是否异常", default=False, db_index=True)
    pattern_id = models.IntegerField("模式ID", null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '日志条目'
        verbose_name_plural = '日志条目'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['server', '-timestamp']),
            models.Index(fields=['level', '-timestamp']),
        ]

    def __str__(self):
        return f"[{self.level}] {self.message[:80]}"


class LogPattern(models.Model):
    server = models.ForeignKey('cmdb.Server', on_delete=models.CASCADE,
        null=True, blank=True, related_name='log_patterns', verbose_name="服务器")
    pattern_template = models.TextField("模式模板")
    pattern_vector = _vector_field(dimensions=1536)
    level = models.CharField("级别", max_length=10, default='ERROR')
    source = models.CharField("来源", max_length=50, default='syslog')
    occurrence_count = models.PositiveIntegerField("出现次数", default=1)
    first_seen = models.DateTimeField("首次出现")
    last_seen = models.DateTimeField("最后出现")
    is_anomaly_pattern = models.BooleanField("异常模式", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '日志模式'
        verbose_name_plural = '日志模式'
        ordering = ['-occurrence_count']

    def __str__(self):
        return f"[{self.level}] {self.pattern_template[:80]} (×{self.occurrence_count})"


class TraceSpan(models.Model):
    STATUS_CHOICES = [('OK', 'OK'), ('ERROR', 'ERROR'), ('UNSET', 'UNSET')]
    trace_id = models.CharField("TraceID", max_length=32, db_index=True)
    span_id = models.CharField("SpanID", max_length=16)
    parent_span_id = models.CharField("ParentSpanID", max_length=16, null=True, blank=True)
    server = models.ForeignKey('cmdb.Server', on_delete=models.CASCADE,
        null=True, blank=True, related_name='trace_spans', verbose_name="服务器")
    service_name = models.CharField("服务名", max_length=100, db_index=True)
    operation = models.CharField("操作", max_length=200)
    start_time = models.DateTimeField("开始时间", db_index=True)
    duration_ms = models.IntegerField("耗时(ms)", default=0)
    status = models.CharField("状态", max_length=10, choices=STATUS_CHOICES, default='UNSET', db_index=True)
    error_message = models.TextField("错误信息", blank=True)
    attributes = models.JSONField("属性", default=dict)
    span_vector = _vector_field(dimensions=1536)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '链路追踪'
        verbose_name_plural = '链路追踪'
        ordering = ['-start_time']
        indexes = [
            models.Index(fields=['service_name', '-start_time']),
            models.Index(fields=['status', '-start_time']),
        ]

    def __str__(self):
        return f"{self.service_name} {self.operation} ({self.duration_ms}ms)"


class WebhookEndpoint(models.Model):
    name = models.CharField(max_length=200)
    url = models.URLField()
    secret = models.CharField(max_length=200, blank=True, default='')
    events = models.JSONField(default=list, help_text="订阅的事件类型: ['alert.fired','alert.resolved','remediation.success','remediation.failed']")
    is_active = models.BooleanField(default=True)
    last_status = models.CharField(max_length=20, blank=True, default='')
    last_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Webhook端点'
        verbose_name_plural = 'Webhook端点'

    def __str__(self):
        return f"{self.name} -> {self.url}"


class CaseVector(models.Model):
    title = models.CharField("案例标题", max_length=200)
    symptoms = models.TextField("症状描述")
    root_cause = models.TextField("根因分析")
    remediation = models.TextField("修复方式")
    confidence = models.FloatField("置信度", default=0.0)
    effectiveness_score = models.FloatField("有效性评分", default=0.0)
    usage_count = models.PositiveIntegerField("使用次数", default=0)
    symptom_vector = _vector_field(dimensions=1536)
    related_alert_rules = models.JSONField("关联告警规则", default=list)
    related_runbook = models.ForeignKey('monitoring.RunbookEntry',
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='case_vectors', verbose_name="关联Runbook")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '历史案例'
        verbose_name_plural = '历史案例'
        ordering = ['-effectiveness_score']

    def __str__(self):
        return f"{self.title} (置信度={self.confidence:.2f}, 有效性={self.effectiveness_score:.1f})"


class MetricBaseline(models.Model):
    server = models.ForeignKey('cmdb.Server', on_delete=models.CASCADE, related_name='metric_baselines', verbose_name="服务器")
    metric_name = models.CharField("指标名", max_length=50)
    hour_of_day = models.IntegerField("小时(0-23)")
    weekday = models.IntegerField("星期(0-6,0=周一)", null=True, blank=True)
    avg_value = models.FloatField("平均值")
    std_dev = models.FloatField("标准差", default=0)
    sample_count = models.IntegerField("样本数", default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '指标基线'
        verbose_name_plural = '指标基线'
        unique_together = ('server', 'metric_name', 'hour_of_day', 'weekday')
        indexes = [
            models.Index(fields=['server', 'metric_name', 'hour_of_day']),
        ]

    def __str__(self):
        return f"{self.server.hostname} {self.metric_name} h={self.hour_of_day} w={self.weekday} avg={self.avg_value:.2f}"
