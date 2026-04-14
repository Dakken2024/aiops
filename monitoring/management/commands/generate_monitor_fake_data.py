import random
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth.models import User

from monitoring.models import (
    AlertRule, AlertEvent, AlertSilenceRule, NotificationLog,
    DetectorConfig, AnomalyHistory, AlertGroup, AlertCorrelationRule,
    RemediationAction, RemediationHistory, RunbookEntry, AgentToken,
    EscalationPolicy, ServiceTopology, SavedDashboard, HealthScore
)
from cmdb.models import Server, ServerGroup


class Command(BaseCommand):
    help = '为 AiOps Monitor 模块生成保险金融行业模拟数据，用于填充 Dashboard 验证功能'

    def add_arguments(self, parser):
        parser.add_argument(
            '--count', type=int, default=50,
            help='基础数据量倍率（默认50，表示中等规模数据集）'
        )
        parser.add_argument(
            '--clean', action='store_true',
            help='执行前清理已有的模拟数据（危险操作！）'
        )
        parser.add_argument(
            '--servers', type=int, default=0,
            help='指定生成的服务器数量（默认按count自动计算）'
        )
        parser.add_argument(
            '--no-input', action='store_true',
            help='跳过确认提示直接执行'
        )

    def handle(self, *args, **options):
        count = options['count']
        clean = options['clean']
        no_input = options['no_input']
        custom_servers = options['servers']

        self.stdout.write(self.style.NOTICE('=' * 60))
        self.stdout.write(self.style.SUCCESS('  🏦  AiOps 保险金融行业模拟数据生成器'))
        self.stdout.write(self.style.NOTICE('=' * 60))

        if clean:
            if not no_input:
                confirm = input('  ⚠️  确定要清理所有已有监控数据吗？输入 YES 确认: ')
                if confirm != 'YES':
                    self.stdout.write(self.style.WARNING('已取消操作。'))
                    return
            self._clean_data()

        server_count = custom_servers or max(8, min(count // 6, 25))

        self.stdout.write(f'\n📊 数据规模配置:')
        self.stdout.write(f'   • 基础倍率: {count}')
        self.stdout.write(f'   • 服务器数量: {server_count}')
        self.stdout.write(f'   • 预计生成数据量: ~{self._estimate_total(count, server_count)} 条记录\n')

        if not no_input:
            confirm = input('  ✅ 是否开始生成？(Y/n): ').strip().lower()
            if confirm == 'n':
                self.stdout.write(self.style.WARNING('已取消操作。'))
                return

        stats = {}
        now = timezone.now()

        try:
            servers = self._generate_servers(server_count, stats)
            alert_rules = self._generate_alert_rules(stats)
            detector_configs = self._generate_detector_configs(stats)
            anomaly_histories = self._generate_anomaly_histories(servers, count, now, stats)
            alert_events = self._generate_alert_events(servers, alert_rules, count, now, stats)
            health_scores = self._generate_health_scores(servers, count, now, stats)
            notification_logs = self._generate_notification_logs(alert_events, count, stats)
            silence_rules = self._generate_silence_rules(servers, stats)
            alert_groups = self._generate_alert_groups(alert_events, stats)
            correlation_rules = self._generate_correlation_rules(stats)
            remediation_actions = self._generate_remediation_actions(stats)
            remediation_histories = self._generate_remediation_histories(alert_events, remediation_actions, stats)
            runbook_entries = self._generate_runbook_entries(stats)
            agent_tokens = self._generate_agent_tokens(servers, stats)
            escalation_policies = self._generate_escalation_policies(stats)
            service_topologies = self._generate_service_topology(servers, stats)
            dashboards = self._generate_dashboards(stats)

            self._print_summary(stats)

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ 生成失败: {str(e)}'))
            raise

    def _estimate_total(self, count, server_count):
        estimate = (server_count +
                   15 + count * 2 + count * 3 + server_count * count // 4 +
                   server_count * count // 2 + count * 5 + count * 8 +
                   count * 3 + count // 2 + count // 3 + 12 + 10 +
                   8 + server_count + 6 + 5 + server_count * 2)
        return estimate

    def _clean_data(self):
        self.stdout.write('\n🧹 正在清理现有监控数据...')
        models_to_clean = [
            HealthScore, NotificationLog, RemediationHistory,
            AnomalyHistory, AlertEvent, AlertGroup,
            AlertSilenceRule, AgentToken, ServiceTopology,
            SavedDashboard, AlertRule, AlertCorrelationRule,
            RemediationAction, RunbookEntry, EscalationPolicy,
            DetectorConfig
        ]
        for model in models_to_clean:
            deleted, _ = model.objects.all().delete()
            if deleted > 0:
                self.stdout.write(f'   ✓ {model._meta.verbose_name}: 清理 {deleted} 条')

    def _generate_servers(self, count, stats):
        self.stdout.write('\n🖥️  [1/17] 生成保险核心系统服务器集群...')

        groups_data = [
            ('保险核心业务集群', None),
            ('理赔处理中心', None),
            ('客户服务平台', None),
            ('风控数据中心', None),
            ('财务结算系统', None),
            ('互联网保险前端', '保险核心业务集群'),
            ('保单管理系统', '保险核心业务集群'),
            ('核保引擎集群', '保险核心业务集群'),
            ('精算计算节点', '风控数据中心'),
            ('反欺诈检测平台', '风控数据中心'),
            ('支付网关服务', '财务结算系统'),
            ('银保对接前置', '财务结算系统'),
            ('移动APP后端', '客户服务平台'),
            ('微信小程序服务', '客户服务平台'),
            ('呼叫中心系统', '客户服务平台'),
        ]

        group_map = {}
        for name, parent_name in groups_data:
            parent = group_map.get(parent_name) if parent_name else None
            group, _ = ServerGroup.objects.get_or_create(name=name, parent=parent)
            group_map[name] = group

        insurance_systems = [
            {'prefix': 'ins-core', 'name': '核心业务服务器', 'group': '保险核心业务集群',
             'specs': [(32, 128), (64, 256), (16, 64)], 'count': max(3, count // 20)},
            {'prefix': 'claim-proc', 'name': '理赔处理节点', 'group': '理赔处理中心',
             'specs': [(16, 64), (32, 128)], 'count': max(2, count // 25)},
            {'prefix': 'cust-svc', 'name': '客户服务节点', 'group': '客户服务平台',
             'specs': [(8, 32), (16, 64), (16, 64)], 'count': max(2, count // 25)},
            {'prefix': 'risk-ctrl', 'name': '风控分析节点', 'group': '风控数据中心',
             'specs': [(32, 128), (64, 256)], 'count': max(1, count // 30)},
            {'prefix': 'fin-settle', 'name': '财务结算节点', 'group': '财务结算系统',
             'specs': [(16, 64), (32, 128)], 'count': max(1, count // 30)},
            {'prefix': 'web-gateway', 'name': 'API网关', 'group': '互联网保险前端',
             'specs': [(8, 32), (16, 64)], 'count': 2},
            {'prefix': 'db-master', 'name': '数据库主库', 'group': '保险核心业务集群',
             'specs': [(64, 512), (128, 1024)], 'count': 1},
            {'prefix': 'db-slave', 'name': '数据库从库', 'group': '保险核心业务集群',
             'specs': [(64, 512), (64, 512)], 'count': 2},
            {'prefix': 'redis-cluster', 'name': 'Redis缓存集群', 'group': '保险核心业务集群',
             'specs': [(16, 64), (32, 128)], 'count': 3},
            {'prefix': 'mq-broker', 'name': '消息队列集群', 'group': '保险核心业务集群',
             'specs': [(16, 64), (32, 128)], 'count': 2},
            {'prefix': 'es-node', 'name': '搜索引擎节点', 'group': '风控数据中心',
             'specs': [(32, 128), (64, 256)], 'count': 3},
            {'prefix': 'hadoop-nn', 'name': 'Hadoop主节点', 'group': '风控数据中心',
             'specs': [(64, 256),], 'count': 1},
            {'prefix': 'hadoop-dn', 'name': 'Hadoop数据节点', 'group': '风控数据中心',
             'specs': [(32, 128), (64, 256)], 'count': max(2, count // 30)},
        ]

        servers = []
        for sys_info in insurance_systems:
            group = group_map.get(sys_info['group'])
            for i in range(sys_info['count']):
                cpu, mem = random.choice(sys_info['specs'])
                hostname = f"{sys_info['prefix']}-{i+1:02d}.insurance.local"
                ip = f"10.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"
                server = Server.objects.create(
                    hostname=hostname,
                    ip_address=ip,
                    cpu_cores=cpu,
                    memory_gb=mem,
                    os_name=random.choice(['CentOS 7.9', 'Ubuntu 20.04', 'RedHat 8.4']),
                    status='Running',
                    provider=random.choices(['aliyun', 'private'], weights=[70, 30])[0],
                    use_agent=random.random() > 0.3,
                    group=group
                )
                servers.append(server)

        stats['servers'] = len(servers)
        self.stdout.write(self.style.SUCCESS(f'   ✓ 已创建 {len(servers)} 台保险业务服务器'))
        return servers

    def _generate_alert_rules(self, stats):
        self.stdout.write('⚠️  [2/17] 生成保险业务预警规则...')

        rules_config = [
            {
                'name': '核心交易系统CPU使用率告警',
                'description': '监控保险核心交易系统的CPU使用率，超过90%时触发P0级告警，确保高并发投保/理赔场景下系统稳定',
                'rule_type': 'threshold',
                'severity': 'P0',
                'metric_name': 'cpu_usage',
                'condition': {'operator': 'gt', 'value': 90},
                'target_all': False,
            },
            {
                'name': '理赔处理队列积压告警',
                'description': '当理赔申请处理队列积压超过阈值时触发告警，影响客户理赔时效体验',
                'rule_type': 'threshold',
                'severity': 'P1',
                'metric_name': 'custom_queue_depth',
                'condition': {'operator': 'gt', 'value': 1000},
                'target_all': False,
            },
            {
                'name': '保单数据库主从延迟告警',
                'description': '保单数据库主从复制延迟过大可能导致数据不一致，影响承保/理赔准确性',
                'rule_type': 'threshold',
                'severity': 'P0',
                'metric_name': 'db_replication_lag',
                'condition': {'operator': 'gt', 'value': 30},
                'target_all': False,
            },
            {
                'name': '支付网关响应时间异常',
                'description': '保费缴纳/理赔打款的支付网关响应时间异常，直接影响资金流转和用户体验',
                'rule_type': 'baseline',
                'severity': 'P1',
                'metric_name': 'response_time',
                'condition': {'multiplier': 2.5},
                'target_all': False,
            },
            {
                'name': '风控模型推理延迟告警',
                'description': '反欺诈/核保风控模型推理延迟过高，影响实时风险决策能力',
                'rule_type': 'trend',
                'severity': 'P1',
                'metric_name': 'model_inference_latency',
                'condition': {'direction': 'up', 'window': 5, 'threshold': 1.5},
                'target_all': False,
            },
            {
                'name': '客户信息查询接口错误率',
                'description': '客户信息查询接口错误率上升，可能影响代理人展业和客服查询效率',
                'rule_type': 'composite',
                'severity': 'P2',
                'metric_name': 'error_rate',
                'condition': {'conditions': [{'field': 'error_rate', 'op': 'gt', 'val': 5}]},
                'target_all': True,
            },
            {
                'name': '磁盘空间不足告警',
                'description': '保单影像/理赔单证存储磁盘空间不足，影响业务连续性',
                'rule_type': 'threshold',
                'severity': 'P1',
                'metric_name': 'disk_usage',
                'condition': {'operator': 'gt', 'value': 85},
                'target_all': True,
            },
            {
                'name': '精算计算任务超时告警',
                'description': '产品定价/准备金计提的精算计算任务执行时间异常',
                'rule_type': 'absence',
                'severity': 'P2',
                'metric_name': 'actuarial_job_heartbeat',
                'condition': {'max_absent_seconds': 3600},
                'target_all': False,
            },
            {
                'name': '银保通对接通道异常检测',
                'description': '与银行保险对接通道的异常流量模式检测，防范潜在安全风险',
                'rule_type': 'anomaly',
                'severity': 'P0',
                'metric_name': 'bank_channel_traffic',
                'condition': {'detector': 'zscore', 'threshold': 3.0},
                'target_all': False,
            },
            {
                'name': '内存使用率持续增长趋势',
                'description': '核心业务系统内存使用率呈现持续上升趋势，可能存在内存泄漏',
                'rule_type': 'trend',
                'severity': 'P2',
                'metric_name': 'mem_usage',
                'condition': {'direction': 'up', 'window': 10, 'threshold': 1.2},
                'target_all': True,
            },
            {
                'name': '网络入站流量突增检测',
                'description': '检测异常的网络流量突增，可能是DDoS攻击或业务量激增',
                'rule_type': 'anomaly',
                'severity': 'P1',
                'metric_name': 'net_in',
                'condition': {'detector': 'iqr', 'k': 2.0},
                'target_all': True,
            },
            {
                'name': 'Redis缓存命中率下降',
                'description': 'Redis缓存命中率下降会导致数据库压力增大，影响保单查询性能',
                'rule_type': 'baseline',
                'severity': 'P2',
                'metric_name': 'redis_hit_rate',
                'condition': {'multiplier': 0.7},
                'target_all': False,
            },
            {
                'name': '消息队列消费者积压',
                'description': 'Kafka/RabbitMQ消息队列消费者处理速度跟不上生产速度',
                'rule_type': 'threshold',
                'severity': 'P1',
                'metric_name': 'consumer_lag',
                'condition': {'operator': 'gt', 'value': 5000},
                'target_all': False,
            },
            {
                'name': 'SSL证书即将过期告警',
                'description': '保险官网/移动端API的SSL证书即将过期，影响用户信任度',
                'rule_type': 'threshold',
                'severity': 'P2',
                'metric_name': 'ssl_cert_remaining_days',
                'condition': {'operator': 'lt', 'value': 30},
                'target_all': True,
            },
            {
                'name': 'API网关4xx/5xx错误率',
                'description': '统一API网关的错误率升高，影响所有下游业务系统的可用性',
                'rule_type': 'composite',
                'severity': 'P1',
                'metric_name': 'api_error_rate',
                'condition': {'conditions': [
                    {'field': 'error_4xx_rate', 'op': 'gt', 'val': 10},
                    {'field': 'error_5xx_rate', 'op': 'gt', 'val': 2}
                ]},
                'target_all': False,
            },
        ]

        rules = []
        for idx, rule_cfg in enumerate(rules_config):
            rule = AlertRule.objects.create(
                name=rule_cfg['name'],
                description=rule_cfg['description'],
                rule_type=rule_cfg['rule_type'],
                severity=rule_cfg['severity'],
                target_all=rule_cfg['target_all'],
                metric_name=rule_cfg['metric_name'],
                condition_config=rule_cfg['condition'],
                evaluate_interval=random.choice([30, 60, 120]),
                lookback_window=random.choice([3, 5, 10]),
                cooldown_seconds=random.choice([60, 180, 300, 600]),
                max_alerts_per_hour=random.choice([5, 10, 20, 30]),
                notify_channels=random.sample(['dingtalk', 'wechat', 'email', 'slack'], k=random.randint(1, 3)),
                notify_template='【{severity}】{rule_name}: {message}',
                trigger_count=random.randint(0, 500),
                last_triggered_at=timezone.now() - timedelta(minutes=random.randint(0, 1440)),
                status=random.choices(['enabled', 'disabled', 'draft'], weights=[80, 15, 5])[0]
            )
            rules.append(rule)

        stats['alert_rules'] = len(rules)
        self.stdout.write(self.style.SUCCESS(f'   ✓ 已创建 {len(rules)} 条保险业务预警规则'))
        return rules

    def _generate_detector_configs(self, stats):
        self.stdout.write('🔍 [3/17] 配置异常检测算法...')

        detectors = [
            {
                'detector_name': 'zscore',
                'params': {'threshold': 2.5, 'min_samples': 30},
                'is_enabled': True,
                'description': 'Z-Score标准化检测器，适用于正态分布的指标如CPU、内存使用率'
            },
            {
                'detector_name': 'iqr',
                'params': {'k': 1.5, 'min_samples': 20},
                'is_enabled': True,
                'description': 'IQR四分位距检测器，抗异常值干扰，适合网络流量等波动较大的指标'
            },
            {
                'detector_name': 'moving_avg',
                'params': {'window': 10, 'factor': 2.0},
                'is_enabled': True,
                'description': '移动平均检测器，适合检测趋势性偏离，如响应时间的渐进恶化'
            },
            {
                'detector_name': 'rate_of_change',
                'params': {'threshold': 0.5, 'window': 5},
                'is_enabled': True,
                'description': '变化率检测器，专门捕捉突变型异常，如瞬时流量洪峰'
            },
            {
                'detector_name': 'composite',
                'params': {'vote_thr': 0.6, 'detectors': ['zscore', 'iqr']},
                'is_enabled': True,
                'description': '复合投票检测器，综合多个检测器结果，降低误报率'
            }
        ]

        created = []
        for det in detectors:
            obj = DetectorConfig.objects.create(**det)
            created.append(obj)

        stats['detector_configs'] = len(created)
        self.stdout.write(self.style.SUCCESS(f'   ✓ 已配置 {len(created)} 个异常检测算法'))
        return created

    def _generate_anomaly_histories(self, servers, count, now, stats):
        self.stdout.write('📈 [4/17] 生成异常检测历史记录...')

        metrics = [
            ('cpu_usage', 'CPU使用率'),
            ('mem_usage', '内存使用率'),
            ('disk_usage', '磁盘使用率'),
            ('response_time', 'API响应时间(ms)'),
            ('error_rate', '错误率(%)'),
            ('throughput', '吞吐量(TPS)'),
            ('queue_depth', '队列深度'),
            ('db_connections', '数据库连接数'),
            ('gc_pause_time', 'GC暂停时间(ms)'),
            ('thread_count', '线程数'),
        ]

        methods = ['zscore', 'iqr', 'moving_avg', 'rate_of_change', 'composite']

        anomalies = []
        anomaly_count = min(len(servers) * count // 4, 800)

        for i in range(anomaly_count):
            server = random.choice(servers)
            metric_name, metric_label = random.choice(metrics)
            method = random.choice(methods)

            detected_at = now - timedelta(
                minutes=random.randint(1, 43200),
                seconds=random.randint(0, 59)
            )

            severity_weights = [('high', 15), ('medium', 50), ('low', 35)]
            severity = random.choices(*zip(*severity_weights))[0]

            base_value = self._get_metric_baseline(metric_name)
            deviation = random.uniform(0.1, 0.8) if severity == 'high' else \
                       random.uniform(0.05, 0.3) if severity == 'medium' else \
                       random.uniform(0.02, 0.15)

            current_value = base_value * (1 + deviation) if random.random() > 0.5 else base_value * (1 - deviation)
            baseline_value = base_value
            deviation_percent = abs(current_value - baseline_value) / baseline_value * 100 if baseline_value > 0 else 0

            raw_values = [base_value + random.uniform(-0.05, 0.05) * base_value for _ in range(random.randint(10, 30))]
            raw_values[-1] = current_value

            anomaly_score = round(random.uniform(0.6, 0.99), 3) if severity == 'high' else \
                           round(random.uniform(0.4, 0.75), 3) if severity == 'medium' else \
                           round(random.uniform(0.2, 0.55), 3)

            if metric_name in ["cpu_usage", "throughput"]:
                cause = "高峰期业务量激增"
            elif metric_name == "mem_usage":
                cause = "内存泄漏或GC频繁"
            elif metric_name == "db_connections":
                cause = "慢SQL导致连接池耗尽"
            elif metric_name == "disk_usage":
                cause = "磁盘IO瓶颈或日志文件膨胀"
            else:
                cause = "外部依赖服务响应缓慢"

            ai_diagnosis_options = [
                f'{metric_label}出现{severity}异常，当前值{current_value:.2f}偏离基线{deviation_percent:.1f}%。'
                f'可能原因：{cause}。',
                f'检测到{metric_label}异常波动，异常分数{anomaly_score:.2f}。'
                f'建议检查相关服务的资源使用情况和最近部署变更。',
                f'{method}算法检测到{metric_label}统计特征显著偏离历史基线，'
                f'需关注是否为周期性业务峰值或突发故障前兆。'
            ]

            anomaly = AnomalyHistory.objects.create(
                server=server,
                metric_name=metric_name,
                detected_at=detected_at,
                severity=severity,
                anomaly_score=anomaly_score,
                method_used=method,
                raw_values=[round(v, 4) for v in raw_values],
                current_value=round(current_value, 4),
                baseline_value=round(baseline_value, 4),
                deviation_percent=round(deviation_percent, 2),
                ai_diagnosis=random.choice(ai_diagnosis_options),
                ai_confidence=round(random.uniform(0.65, 0.98), 2),
                ai_analyzed_at=detected_at + timedelta(seconds=random.randint(5, 120))
            )
            anomalies.append(anomaly)

        stats['anomaly_histories'] = len(anomalies)
        self.stdout.write(self.style.SUCCESS(f'   ✓ 已生成 {len(anomalies)} 条异常检测记录'))
        return anomalies

    def _get_metric_baseline(self, metric_name):
        baselines = {
            'cpu_usage': random.uniform(45, 70),
            'mem_usage': random.uniform(55, 75),
            'disk_usage': random.uniform(50, 72),
            'response_time': random.uniform(150, 500),
            'error_rate': random.uniform(0.5, 2.0),
            'throughput': random.uniform(800, 2500),
            'queue_depth': random.uniform(100, 500),
            'db_connections': random.uniform(50, 150),
            'gc_pause_time': random.uniform(20, 80),
            'thread_count': random.uniform(200, 500),
        }
        return baselines.get(metric_name, 50.0)

    def _generate_alert_events(self, servers, alert_rules, count, now, stats):
        self.stdout.write('🚨 [5/17] 生成告警事件...')

        severities = ['P0', 'P1', 'P2', 'P3']
        statuses = ['firing', 'resolved', 'acknowledged', 'silenced']
        status_weights = [25, 45, 20, 10]

        events = []
        event_count = min(len(servers) * count // 2, 1500)

        for i in range(event_count):
            rule = random.choice(alert_rules)
            server = random.choice(servers)
            severity = rule.severity if random.random() > 0.2 else random.choice(severities)
            status = random.choices(statuses, weights=status_weights)[0]

            fired_at = now - timedelta(
                minutes=random.randint(1, 20160),
                seconds=random.randint(0, 59)
            )

            threshold = rule.condition_config.get('value') or rule.condition_config.get('multiplier', 0) * 50
            base_val = self._get_metric_baseline(rule.metric_name)
            current_value = base_val * random.uniform(1.1, 2.0) if severity in ['P0', 'P1'] else base_val * random.uniform(1.01, 1.2)

            messages = [
                f'{server.hostname} 的 {rule.metric_name} 当前值为 {current_value:.2f}，'
                f'{"超过阈值" if rule.rule_type == "threshold" else "偏离基线"} {threshold}',
                f'【保险业务告警】{rule.name} 在 {server.hostname} 上触发，'
                f'当前值: {current_value:.2f}, 阈值: {threshold}',
                f'检测到 {server.hostname} 出现{severity}级别异常: {rule.metric_name}={current_value:.2f}',
            ]

            detail = {
                'server_hostname': server.hostname,
                'server_ip': str(server.ip_address),
                'metric': rule.metric_name,
                'threshold': threshold,
                'current': round(current_value, 4),
                'rule_id': rule.id,
                'rule_type': rule.rule_type,
                'business_context': random.choice([
                    '高峰期投保请求激增',
                    '批量理赔作业执行中',
                    '月末财务结算期间',
                    '精算模型批量运行',
                    '银保对账任务进行中',
                    '保单续费提醒推送',
                    '代理人业绩统计计算',
                    '监管报表生成任务'
                ])
            }

            resolved_at = fired_at + timedelta(
                minutes=random.randint(5, 1440)
            ) if status == 'resolved' else None

            acknowledged_at = fired_at + timedelta(
                minutes=random.randint(1, 60)
            ) if status == 'acknowledged' else None

            notification_log_entry = [{
                'channel': random.choice(['dingtalk', 'wechat', 'email']),
                'sent_at': (fired_at + timedelta(seconds=random.randint(1, 30))).isoformat(),
                'status': 'sent',
                'recipient': 'ops-team@insurance.com'
            }] if random.random() > 0.3 else []

            event = AlertEvent.objects.create(
                rule=rule,
                server=server,
                status=status,
                severity=severity,
                metric_name=rule.metric_name,
                current_value=round(current_value, 4),
                threshold_value=float(threshold) if isinstance(threshold, (int, float)) else None,
                message=random.choice(messages),
                detail=detail,
                fired_at=fired_at,
                resolved_at=resolved_at,
                acknowledged_at=acknowledged_at,
                notification_log=notification_log_entry
            )
            events.append(event)

        stats['alert_events'] = len(events)
        self.stdout.write(self.style.SUCCESS(f'   ✓ 已生成 {len(events)} 条告警事件'))
        return events

    def _generate_health_scores(self, servers, count, now, stats):
        self.stdout.write('💚 [6/17] 生成健康评分记录...')

        grade_choices = ['A', 'B', 'C', 'D', 'F']
        grade_weights = [40, 30, 18, 9, 3]

        scores = []

        for server in servers:
            days_of_data = random.randint(7, 30)
            for day_offset in range(days_of_data):
                scored_at = now - timedelta(days=day_offset, hours=random.randint(0, 23))

                grade = random.choices(grade_choices, weights=grade_weights)[0]

                if grade == 'A':
                    overall = random.uniform(90, 100)
                    cpu_score = random.uniform(85, 100)
                    mem_score = random.uniform(85, 100)
                    disk_score = random.uniform(85, 100)
                    network_score = random.uniform(88, 100)
                    availability_score = random.uniform(95, 100)
                    alert_penalty = random.uniform(0, 5)
                    anomaly_penalty = random.uniform(0, 3)
                elif grade == 'B':
                    overall = random.uniform(75, 89)
                    cpu_score = random.uniform(70, 89)
                    mem_score = random.uniform(70, 89)
                    disk_score = random.uniform(70, 89)
                    network_score = random.uniform(75, 92)
                    availability_score = random.uniform(90, 98)
                    alert_penalty = random.uniform(3, 10)
                    anomaly_penalty = random.uniform(2, 6)
                elif grade == 'C':
                    overall = random.uniform(60, 74)
                    cpu_score = random.uniform(55, 74)
                    mem_score = random.uniform(55, 74)
                    disk_score = random.uniform(55, 74)
                    network_score = random.uniform(60, 80)
                    availability_score = random.uniform(85, 95)
                    alert_penalty = random.uniform(8, 15)
                    anomaly_penalty = random.uniform(5, 10)
                elif grade == 'D':
                    overall = random.uniform(45, 59)
                    cpu_score = random.uniform(40, 59)
                    mem_score = random.uniform(40, 59)
                    disk_score = random.uniform(40, 59)
                    network_score = random.uniform(45, 65)
                    availability_score = random.uniform(78, 90)
                    alert_penalty = random.uniform(12, 22)
                    anomaly_penalty = random.uniform(8, 15)
                else:
                    overall = random.uniform(20, 44)
                    cpu_score = random.uniform(15, 44)
                    mem_score = random.uniform(15, 44)
                    disk_score = random.uniform(15, 44)
                    network_score = random.uniform(20, 50)
                    availability_score = random.uniform(65, 82)
                    alert_penalty = random.uniform(20, 35)
                    anomaly_penalty = random.uniform(12, 22)

                score = HealthScore.objects.create(
                    server=server,
                    scored_at=scored_at,
                    overall_score=round(overall, 2),
                    cpu_score=round(cpu_score, 2),
                    mem_score=round(mem_score, 2),
                    disk_score=round(disk_score, 2),
                    network_score=round(network_score, 2),
                    availability_score=round(availability_score, 2),
                    alert_penalty=round(alert_penalty, 2),
                    anomaly_penalty=round(anomaly_penalty, 2),
                    grade=grade
                )
                scores.append(score)

        stats['health_scores'] = len(scores)
        self.stdout.write(self.style.SUCCESS(f'   ✓ 已生成 {len(scores)} 条健康评分记录'))
        return scores

    def _generate_notification_logs(self, alert_events, count, stats):
        self.stdout.write('📧 [7/17] 生成通知发送记录...')

        channels = ['dingtalk', 'wechat', 'email', 'slack', 'webhook']
        statuses = ['sent', 'failed', 'retrying']
        status_weights = [85, 10, 5]

        logs = []
        log_count = min(len(alert_events) * 3 // 4, count * 5)

        sampled_events = random.sample(alert_events, min(log_count, len(alert_events)))

        for event in sampled_events:
            num_notifications = random.randint(1, 3)
            for _ in range(num_notifications):
                channel = random.choice(channels)
                status = random.choices(statuses, weights=status_weights)[0]

                recipient_configs = {
                    'dingtalk': {'type': 'group', 'name': '保险运维群', 'webhook': 'https://oapi.dingtalk.com/robot/send?access_token=xxx'},
                    'wechat': {'type': 'group', 'name': 'AIOps告警群'},
                    'email': {'to': ['ops@insurance.com', 'oncall@insurance.com'], 'cc': ['manager@insurance.com']},
                    'slack': {'channel': '#ops-alerts', 'usernames': ['@oncall-engineer']},
                    'webhook': {'url': 'https://hooks.example.com/alert', 'method': 'POST'}
                }

                content_summary = (
                    f"[{event.severity}] {event.rule.name}\n"
                    f"服务器: {event.server.hostname}\n"
                    f"指标: {event.metric_name} = {event.current_value:.2f}\n"
                    f"时间: {event.fired_at:%Y-%m-%d %H:%M:%S}"
                )

                error_message = ''
                if status == 'failed':
                    error_messages = [
                        '钉钉Webhook调用超时',
                        '企业微信access_token过期',
                        '邮件服务器连接拒绝',
                        'Slack API Rate Limit',
                        '目标Webhook返回500错误'
                    ]
                    error_message = random.choice(error_messages)

                log = NotificationLog.objects.create(
                    alert_event=event,
                    channel=channel,
                    status=status,
                    recipient=recipient_configs.get(channel, {}),
                    content_summary=content_summary,
                    error_message=error_message,
                    retry_count=random.randint(0, 3) if status == 'retrying' else 0,
                    sent_at=event.fired_at + timedelta(seconds=random.randint(1, 300))
                )
                logs.append(log)

        stats['notification_logs'] = len(logs)
        self.stdout.write(self.style.SUCCESS(f'   ✓ 已生成 {len(logs)} 条通知记录'))
        return logs

    def _generate_silence_rules(self, servers, stats):
        self.stdout.write('🔇 [8/17] 生成静默规则...')

        silence_configs = [
            {
                'name': '精算批处理窗口期静默',
                'match_severity': 'P2,P3',
                'match_rule_name': '',
                'comment': '每月初精算模型批量运行期间，临时屏蔽低优先级CPU/内存告警'
            },
            {
                'name': '理赔高峰期非关键告警静默',
                'match_severity': 'P3',
                'match_rule_name': '',
                'server': random.choice(servers),
                'comment': '每周一理赔高峰期，在理赔处理节点上静默提示级告警'
            },
            {
                'name': '维护窗口全服静默',
                'match_severity': '',
                'match_rule_name': '',
                'server': random.choice(servers),
                'comment': '计划内版本升级维护窗口'
            },
            {
                'name': '银保对账时段特定规则静默',
                'match_severity': 'P1,P2',
                'match_rule_name': '',
                'comment': '每日凌晨银保对账期间，暂时屏蔽部分性能告警'
            },
            {
                'name': '新上线系统观察期静默',
                'match_severity': 'P2,P3',
                'match_rule_name': '',
                'server': random.choice(servers),
                'comment': '新上线的互联网保险前端服务观察期内调整告警阈值'
            },
        ]

        silences = []
        now = timezone.now()

        for config in silence_configs:
            is_active = random.random() > 0.3
            start_offset = random.randint(-168, 48)
            duration_hours = random.randint(2, 72)

            start_time = now + timedelta(hours=start_offset)
            end_time = start_time + timedelta(hours=duration_hours)

            try:
                user = User.objects.first()
            except Exception:
                user = None

            silence = AlertSilenceRule.objects.create(
                name=config['name'],
                match_severity=config['match_severity'],
                match_rule_name=config['match_rule_name'],
                match_server=config.get('server'),
                start_time=start_time,
                end_time=end_time,
                comment=config['comment'],
                is_active=is_active and end_time > now,
                created_by=user
            )
            silences.append(silence)

        stats['silence_rules'] = len(silences)
        self.stdout.write(self.style.SUCCESS(f'   ✓ 已创建 {len(silences)} 条静默规则'))
        return silences

    def _generate_alert_groups(self, alert_events, stats):
        self.stdout.write('📦 [9/17] 生成告警聚合组...')

        group_templates = [
            {
                'name': '核心交易系统故障组',
                'pattern_filter': lambda e: 'core' in e.server.hostname.lower() and e.severity in ['P0', 'P1'],
                'root_cause_hint': '核心交易系统可能出现性能瓶颈或服务不可用'
            },
            {
                'name': '数据库集群异常组',
                'pattern_filter': lambda e: 'db-' in e.server.hostname.lower() or e.metric_name.startswith('db_'),
                'root_cause_hint': '数据库集群负载过高或主从同步异常'
            },
            {
                'name': '存储子系统告警组',
                'pattern_filter': lambda e: e.metric_name in ['disk_usage', 'disk_io_wait'],
                'root_cause_hint': '存储子系统容量不足或IO性能瓶颈'
            },
            {
                'name': '网络层异常组',
                'pattern_filter': lambda e: e.metric_name in ['net_in', 'net_out', 'packet_loss'],
                'root_cause_hint': '网络设备故障或带宽拥塞'
            },
            {
                'name': '应用服务降级组',
                'pattern_filter': lambda e: e.metric_name in ['error_rate', 'response_time', 'throughput']
                                     and e.severity in ['P1', 'P2'],
                'root_cause_hint': '应用服务出现性能降级或错误率上升'
            },
            {
                'name': '保险业务高峰期告警组',
                'pattern_filter': lambda e: '高峰期' in str(e.detail.get('business_context', '')),
                'root_cause_hint': '业务高峰期资源竞争导致的系统性告警'
            },
        ]

        groups = []
        now = timezone.now()

        for template in group_templates:
            matching_events = [e for e in alert_events if template['pattern_filter'](e)]
            if len(matching_events) >= 2:
                fingerprint = uuid.uuid4().hex[:16]
                first_event = min(matching_events, key=lambda e: e.fired_at)
                last_event = max(matching_events, key=lambda e: e.fired_at)

                is_resolved = all(e.status == 'resolved' for e in matching_events[-5:])

                group = AlertGroup.objects.create(
                    name=template['name'],
                    fingerprint=fingerprint,
                    status='resolved' if is_resolved else 'firing',
                    severity=max((e.severity for e in matching_events[:10]), key=lambda s: ['P0','P1','P2','P3'].index(s)),
                    alert_count=len(matching_events),
                    first_fired_at=first_event.fired_at,
                    last_fired_at=last_event.fired_at,
                    resolved_at=last_event.resolved_at if is_resolved else None
                )
                groups.append(group)

        stats['alert_groups'] = len(groups)
        self.stdout.write(self.style.SUCCESS(f'   ✓ 已创建 {len(groups)} 个告警聚合组'))
        return groups

    def _generate_correlation_rules(self, stats):
        self.stdout.write('🔗 [10/17] 生成告警关联规则...')

        correlation_configs = [
            {
                'name': '数据库主从延迟与查询超时关联',
                'description': '当数据库主从复制延迟升高时，通常伴随读查询超时增加',
                'trigger_patterns': {'primary_metric': 'db_replication_lag', 'correlated_metrics': ['response_time']},
                'root_cause_hint': '数据库主从同步延迟导致从库读取超时',
                'suggested_action': '检查主库写入负载，考虑读写分离优化或升级从库硬件',
                'confidence_weight': 0.85
            },
            {
                'name': 'CPU飙升与响应时间恶化关联',
                'description': 'CPU使用率持续高位会导致API响应时间显著增加',
                'trigger_patterns': {'primary_metric': 'cpu_usage', 'correlated_metrics': ['response_time', 'throughput']},
                'root_cause_hint': 'CPU资源争抢导致业务线程处理延迟',
                'suggested_action': '排查高CPU进程，考虑水平扩容或优化慢SQL/复杂计算',
                'confidence_weight': 0.9
            },
            {
                'name': '内存压力与GC频繁关联',
                'description': '内存使用率过高会触发频繁Full GC，导致系统停顿',
                'trigger_patterns': {'primary_metric': 'mem_usage', 'correlated_metrics': ['gc_pause_time']},
                'root_cause_hint': 'JVM堆内存不足导致Full GC频率增加',
                'suggested_action': '调整JVM堆大小，分析内存泄漏或优化数据缓存策略',
                'confidence_weight': 0.88
            },
            {
                'name': '磁盘满与IO等待关联',
                'description': '磁盘空间不足会导致IO性能急剧下降',
                'trigger_patterns': {'primary_metric': 'disk_usage', 'correlated_metrics': ['disk_io_wait']},
                'root_cause_hint': '磁盘空间耗尽导致文件系统性能严重退化',
                'suggested_action': '清理日志/临时文件，扩容磁盘或迁移数据到新存储',
                'confidence_weight': 0.82
            },
            {
                'name': '网络流量突增与带宽拥塞关联',
                'description': '入站流量激增可能导致网络带宽饱和',
                'trigger_patterns': {'primary_metric': 'net_in', 'correlated_metrics': ['packet_loss', 'response_time']},
                'root_cause_hint': '网络带宽达到上限导致丢包和延迟增加',
                'suggested_action': '检查是否为DDoS攻击或业务推广带来的正常流量增长，必要时扩容带宽',
                'confidence_weight': 0.75
            },
            {
                'name': '消息队列积压与消费者异常关联',
                'description': '消息队列积压通常意味着消费者处理能力不足或故障',
                'trigger_patterns': {'primary_metric': 'consumer_lag', 'correlated_metrics': ['error_rate']},
                'root_cause_hint': '消息队列消费者处理速度跟不上或出现消费异常',
                'suggested_action': '检查消费者服务健康状态，增加消费者实例或优化消费逻辑',
                'confidence_weight': 0.87
            },
            {
                'name': '保险核心交易全链路故障关联',
                'description': '核心交易系统的多维度指标同时异常表明系统性故障',
                'trigger_patterns': {'primary_metric': 'throughput', 'correlated_metrics': ['error_rate', 'cpu_usage', 'response_time']},
                'root_cause_hint': '保险核心交易链路出现系统性故障，可能涉及多个依赖服务',
                'suggested_action': '启动应急响应流程，检查核心交易链路的各依赖服务状态，准备切换备用系统',
                'confidence_weight': 0.92
            },
            {
                'name': '理赔处理系统性能退化关联',
                'description': '理赔处理节点的多项性能指标同时下降',
                'trigger_patterns': {'primary_metric': 'custom_queue_depth', 'correlated_metrics': ['response_time', 'cpu_usage']},
                'root_cause_hint': '理赔申请量超过系统处理能力或存在处理逻辑瓶颈',
                'suggested_action': '监控理赔作业队列，临时增加处理节点或启用批量处理优化',
                'confidence_weight': 0.83
            },
        ]

        rules = []
        for config in correlation_configs:
            rule = AlertCorrelationRule.objects.create(
                name=config['name'],
                description=config['description'],
                trigger_patterns=config['trigger_patterns'],
                root_cause_hint=config['root_cause_hint'],
                suggested_action=config['suggested_action'],
                confidence_weight=config['confidence_weight'],
                is_active=random.random() > 0.15
            )
            rules.append(rule)

        stats['correlation_rules'] = len(rules)
        self.stdout.write(self.style.SUCCESS(f'   ✓ 已创建 {len(rules)} 条告警关联规则'))
        return rules

    def _generate_remediation_actions(self, stats):
        self.stdout.write('🔧 [11/17] 生成自动修复动作...')

        action_configs = [
            {
                'name': '重启保险核心服务',
                'action_type': 'service_restart',
                'target_command': 'systemctl restart insurance-core-service',
                'severity_filter': 'P0,P1',
                'timeout_seconds': 120,
                'is_dangerous': True,
            },
            {
                'name': '清理保单影像临时文件',
                'action_type': 'disk_cleanup',
                'target_command': '/usr/local/bin/cleanup_policy_images.sh --older-than 7days',
                'severity_filter': 'P1,P2',
                'timeout_seconds': 600,
                'is_dangerous': False,
            },
            {
                'name': '执行数据库连接池回收脚本',
                'action_type': 'script',
                'target_command': '/opt/scripts/db_connection_pool_recycle.py --pool-name insurance-main',
                'severity_filter': 'P1',
                'timeout_seconds': 180,
                'is_dangerous': True,
            },
            {
                'name': '扩展理赔处理节点',
                'action_type': 'scale_out',
                'target_command': 'kubectl scale deployment claim-processor --replicas=$(($(kubectl get deployment claim-processor -o jsonpath={.spec.replicas}) + 2))',
                'severity_filter': 'P0,P1',
                'timeout_seconds': 300,
                'is_dangerous': False,
            },
            {
                'name': '调用银保通道健康检查Webhook',
                'action_type': 'webhook',
                'target_command': 'https://internal-gateway.insurance.local/api/bank-channel/health-check',
                'severity_filter': 'P1,P2',
                'timeout_seconds': 30,
                'is_dangerous': False,
            },
            {
                'name': '重启Redis缓存集群节点',
                'action_type': 'service_restart',
                'target_command': 'redis-cli --no-auth-warning -a $REDIS_PASS cluster failover',
                'severity_filter': 'P0',
                'timeout_seconds': 60,
                'is_dangerous': True,
            },
            {
                'name': '清理精算模型临时输出目录',
                'action_type': 'disk_cleanup',
                'target_command': 'find /data/actuarial/temp -type f -mtime +3 -delete',
                'severity_filter': 'P2',
                'timeout_seconds': 300,
                'is_dangerous': False,
            },
            {
                'name': '执行OOM Killer防护脚本',
                'action_type': 'script',
                'target_command': '/opt/scripts/oom_protection.sh --threshold 85 --grace-period 300',
                'severity_filter': 'P0,P1',
                'timeout_seconds': 90,
                'is_dangerous': True,
            },
            {
                'name': '重置风控模型推理缓存',
                'action_type': 'custom',
                'target_command': 'curl -X POST http://localhost:8080/risk-model/cache/invalidate --header "Authorization: Bearer $INTERNAL_TOKEN"',
                'severity_filter': 'P1,P2',
                'timeout_seconds': 30,
                'is_dangerous': False,
            },
            {
                'name': '触发支付网关熔断恢复',
                'action_type': 'webhook',
                'target_command': 'https://payment-gateway.insurance.local/api/circuit-breaker/reset',
                'severity_filter': 'P0',
                'timeout_seconds': 15,
                'is_dangerous': True,
            },
        ]

        actions = []
        for config in action_configs:
            action = RemediationAction.objects.create(
                name=config['name'],
                action_type=config['action_type'],
                target_command=config['target_command'],
                severity_filter=config['severity_filter'],
                timeout_seconds=config['timeout_seconds'],
                max_retries=random.randint(1, 3),
                is_dangerous=config['is_dangerous'],
                is_active=random.random() > 0.1
            )
            actions.append(action)

        stats['remediation_actions'] = len(actions)
        self.stdout.write(self.style.SUCCESS(f'   ✓ 已创建 {len(actions)} 个修复动作'))
        return actions

    def _generate_remediation_histories(self, alert_events, remediation_actions, stats):
        self.stdout.write('📋 [12/17] 生成修复执行记录...')

        status_choices = ['pending', 'running', 'success', 'failed', 'timeout', 'cancelled']
        status_weights = [5, 8, 55, 18, 10, 4]

        histories = []
        history_count = len(alert_events) // 4

        sampled_events = random.sample(alert_events, min(history_count, len(alert_events)))

        for event in sampled_events:
            if event.status not in ['firing', 'acknowledged'] or random.random() > 0.4:
                continue

            action = random.choice(remediation_actions)
            if not action.matches_severity(event.severity):
                continue

            status = random.choices(status_choices, weights=status_weights)[0]

            started_at = event.fired_at + timedelta(minutes=random.randint(1, 30))

            output_templates = {
                'success': [
                    '✅ 操作成功完成，服务已恢复正常运行状态',
                    '✅ 清理完成，释放空间约 15.2 GB',
                    '✅ 服务重启成功，当前运行状态 healthy',
                    '✅ 扩容完成，新增2个处理节点已加入集群',
                    '✅ Webhook调用成功，返回状态码200'
                ],
                'failed': [
                    '❌ 执行失败：权限不足，请使用sudo执行',
                    '❌ 执行失败：目标服务无响应，连接超时',
                    '❌ 执行失败：磁盘仍处于只读模式',
                    '❌ 脚本执行错误：exit code 1，详见日志'
                ],
                'timeout': [
                    '⏱️ 执行超时：操作在规定时间内未完成，已终止'
                ]
            }

            error_messages = [
                'Permission denied: 需要运维管理员权限执行此操作',
                'Connection refused: 目标服务端口不可达',
                'Disk read-only filesystem: 无法在只读文件系统上执行写操作',
                'Kubernetes API error: 扩容请求被HPA限制拒绝',
                'Authentication failed: 内部Token已过期'
            ]

            finished_at = started_at + timedelta(
                minutes=random.randint(1, 30)
            ) if status != 'running' and status != 'pending' else None

            output = ''
            error_message = ''

            if status == 'success':
                output = random.choice(output_templates['success'])
            elif status == 'failed':
                output = random.choice(output_templates['failed'])
                error_message = random.choice(error_messages)
            elif status == 'timeout':
                output = random.choice(output_templates['timeout'])

            history = RemediationHistory.objects.create(
                alert_event=event,
                action=action,
                status=status,
                started_at=started_at,
                finished_at=finished_at,
                output=output,
                error_message=error_message
            )
            histories.append(history)

        stats['remediation_histories'] = len(histories)
        self.stdout.write(self.style.SUCCESS(f'   ✓ 已生成 {len(histories)} 条修复记录'))
        return histories

    def _generate_runbook_entries(self, stats):
        self.stdout.write('📚 [13/17] 生成运维知识库条目...')

        runbook_configs = [
            {
                'title': '保险核心交易系统CPU使用率飙升至100%处置手册',
                'problem_pattern': {'metric': 'cpu_usage', 'condition': 'gt', 'value': 95, 'duration_min': 5},
                'solution': '''## 处置步骤

### 1. 立即确认影响范围
- 检查投保、理赔、保全等核心交易接口的响应时间和错误率
- 确认是否有正在进行的大批量业务（如月末结算、批处理）

### 2. 快速定位高CPU进程
\`\`\`bash
top -bn1 | head -20
ps aux --sort=-%cpu | head -15
\`\`\`

### 3. 常见原因及处置
- **Java应用Full GC**: `jstat -gc <pid> 1000` 观察GC情况，考虑紧急扩容
- **数据库慢SQL**: 开启slow query log，`SHOW PROCESSLIST` 定位阻塞会话
- **精算批处理任务**: 确认是否为计划内任务，可临时降低优先级

### 4. 应急措施
- 如确认非预期负载：检查是否遭受攻击，准备启用WAF规则
- 临时方案：通过API网关限流保护后端服务
- 必要时：联系架构组评估紧急扩容方案''',
                'category': 'application',
                'tags': 'CPU,核心交易,高性能,应急响应',
                'effectiveness_score': 9.2,
                'usage_count': random.randint(50, 200)
            },
            {
                'title': '保单数据库主从复制延迟过大排查指南',
                'problem_pattern': {'metric': 'db_replication_lag', 'condition': 'gt', 'value': 30},
                'solution': '''## 排查流程

### 1. 确认延迟程度
\`\`\`sql
SHOW SLAVE STATUS\\G
-- 关注 Seconds_Behind_Master 和 Exec_Master_Log_Pos
\`\`\`

### 2. 常见原因
- **大事务阻塞**: 检查是否有长时间运行的批量更新（如保单批量导入）
- **从库负载过高**: 从库承担过多读请求，导致relay log应用速度慢
- **网络抖动**: 主从之间网络质量不稳定

### 3. 处置方案
- 紧急：将从库暂时设为只读，减少读取压力
- 优化：拆分大事务为小批次执行
- 长期：评估引入MGR或Galera集群方案''',
                'category': 'database',
                'tags': 'MySQL,主从复制,数据库,延迟,高可用',
                'effectiveness_score': 8.7,
                'usage_count': random.randint(30, 150)
            },
            {
                'title': '理赔处理队列积压快速恢复SOP',
                'problem_pattern': {'metric': 'custom_queue_depth', 'condition': 'gt', 'value': 800},
                'solution': '''## 理赔队列积压处置

### 当前背景
理赔处理是保险公司最关键的业务流程之一，积压直接影响客户满意度和监管合规。

### 应急响应步骤
1. **评估积压规模**: 查询当前队列深度和平均等待时间
2. **确认处理节点状态**: 检查claim-proc节点CPU/内存/线程池
3. **临时扩容**: 
   \`\`\`bash
   kubectl scale deployment claim-processor --replicas=10
   \`\`\`
4. **优先级调整**: 将VIP客户和小额快赔案件提升优先级
5. **通知客服**: 同步预计恢复时间，准备FAQ话术

### 根因排查方向
- 是否有新的产品上线导致理赔量激增？
- 第三方数据源（医院、车管所）接口是否正常？
- 规则引擎是否有性能退化？''',
                'category': 'application',
                'tags': '理赔,队列,积压,客户体验,SOP',
                'effectiveness_score': 9.5,
                'usage_count': random.randint(80, 250)
            },
            {
                'title': '支付网关响应时间异常排查手册',
                'problem_pattern': {'metric': 'response_time', 'condition': 'gt', 'value': 5000, 'service': 'payment-gateway'},
                'solution': '''## 支付网关性能问题排查

### 影响范围
保费缴纳、理赔打款、退保退款等所有资金流转场景

### 排查清单
1. **第三方渠道状态**: 检查银联、微信、支付宝等渠道网关状态
2. **网络连通性**: `traceroute` 到各支付渠道的延迟
3. **签名验签耗时**: RSA/SM2加解密操作是否成为瓶颈
4. **数据库锁**: 支付流水表是否存在行锁竞争

### 常见优化点
- 引入异步支付结果通知机制
- 对账任务避开业务高峰期
- 缓存常用费率和产品信息''',
                'category': 'network',
                'tags': '支付,响应时间,网关,第三方,性能优化',
                'effectiveness_score': 8.1,
                'usage_count': random.randint(25, 100)
            },
            {
                'title': 'Redis缓存命中率骤降应急处置',
                'problem_pattern': {'metric': 'redis_hit_rate', 'condition': 'lt', 'value': 70},
                'solution': '''## Redis缓存问题诊断

### 现象表现
- 保单查询接口P99延迟从50ms升至2s+
- 数据库CPU使用率显著上升
- 客户端反馈"系统较慢"

### 诊断命令
\`\`\`bash
redis-cli info stats | grep hits
redis-cli info memory | grep used_memory_human
redis-cli --bigkeys
\`\`\`

### 常见原因
1. **缓存穿透**: 查询不存在的保单号，每次都打到DB
2. **缓存雪崩**: 大量key同时过期（如批量导入后统一设置TTL）
3. **内存淘汰**: maxmemory达到上限，频繁evict

### 解决方案
- 布隆过滤器防止穿透
- TTL添加随机偏移避免雪崩
- 监控内存使用率，提前预警扩容''',
                'category': 'storage',
                'tags': 'Redis,缓存,命中率,性能,内存管理',
                'effectiveness_score': 8.9,
                'usage_count': random.randint(40, 130)
            },
            {
                'title': '反欺诈风控模型推理延迟升高的处置方案',
                'problem_pattern': {'metric': 'model_inference_latency', 'condition': 'gt', 'value': 500},
                'solution': '''## 风控模型性能问题

### 业务影响
核保、理赔审核环节的实时风险评分延迟增高，影响客户实时体验

### 可能原因
1. **GPU资源不足**: 模型推理需要GPU加速，显存或算力不够
2. **输入特征膨胀**: 新增了过多特征维度，推理时间线性增长
3. **模型版本回滚**: 新版本模型比旧版更复杂

### 优化建议
- 模型量化：FP32 → INT8，减少计算量
- 批量推理：将单个请求改为mini-batch
- 结果缓存：相同特征的请求直接返回缓存结果
- 降级策略：超时时返回默认评分+人工复核标记''',
                'category': 'application',
                'tags': '风控,机器学习,模型推理,延迟,GPU',
                'effectiveness_score': 7.8,
                'usage_count': random.randint(15, 60)
            },
            {
                'title': 'SSL证书即将过期告警处理流程',
                'problem_pattern': {'metric': 'ssl_cert_remaining_days', 'condition': 'lt', 'value': 30},
                'solution': '''## SSL证书续期操作指南

### 涉及域名
- www.insurance.com (官网)
- api.insurance.com (移动端API)
- agent.insurance.com (代理人展业平台)
- claim.insurance.com (理赔自助入口)

### 续期步骤
1. 向CA提交CSR（推荐Let's Encrypt免费证书或购买企业级OV证书）
2. 在负载均衡层更新证书文件
3. 验证证书链完整性
4. 更新监控系统的证书到期提醒阈值

### 注意事项
- 提前14天开始续期流程，留出验证缓冲时间
- 测试环境先验证，再推生产
- 通知安全团队进行合规审计''',
                'category': 'security',
                'tags': 'SSL,证书,安全,HTTPS,合规',
                'effectiveness_score': 9.0,
                'usage_count': random.randint(35, 90)
            },
            {
                'title': 'Kubernetes Pod OOMKilled事件分析与预防',
                'problem_pattern': {'k8s_event': 'OOMKilled', 'container_state': 'waiting'},
                'solution': '''## 容器OOM排查

### 诊断信息收集
\`\`\`bash
kubectl describe pod <pod-name> | grep -A10 "Last State"
kubectl top pods --sort-by=memory
kubectl logs <pod-name> --previous | tail -100
\`\`\`

### 常见场景及解决方案

#### 场景1: Java应用内存泄漏
- 启用 `-XX:+HeapDumpOnOutOfMemoryError`
- 使用MAT工具分析dump文件
- 重点检查：ThreadLocal缓存、大对象集合

#### 场景2: 保险影像文件处理
- 理赔影像上传/预览功能加载大文件到内存
- 改用流式处理或外部对象存储

#### 场景3: requests/limits配置不合理
- 根据实际使用量调整resource limits
- 设置合理的Memory Request（建议峰值的70%）''',
                'category': 'general',
                'tags': 'Kubernetes,OOM,内存,容器,Pod',
                'effectiveness_score': 8.5,
                'usage_count': random.randint(45, 120)
            },
        ]

        try:
            user = User.objects.first()
        except Exception:
            user = None

        entries = []
        for config in runbook_configs:
            entry = RunbookEntry.objects.create(
                title=config['title'],
                problem_pattern=config['problem_pattern'],
                solution=config['solution'],
                category=config['category'],
                tags=config['tags'],
                effectiveness_score=config['effectiveness_score'],
                usage_count=config['usage_count'],
                created_by=user,
                is_published=True
            )
            entries.append(entry)

        stats['runbook_entries'] = len(entries)
        self.stdout.write(self.style.SUCCESS(f'   ✓ 已创建 {len(entries)} 条运维知识条目'))
        return entries

    def _generate_agent_tokens(self, servers, stats):
        self.stdout.write('🤖 [14/17] 生成Agent Token...')

        tokens = []
        agent_servers = [s for s in servers if s.use_agent]

        for server in agent_servers[:max(5, len(agent_servers) * 2 // 3)]:
            token = AgentToken.objects.create(
                name=f'{server.hostname} Monitor Agent',
                token=uuid.uuid4().hex,
                server=server,
                is_active=random.random() > 0.15,
                last_seen_at=timezone.now() - timedelta(minutes=random.randint(1, 1440)) if random.random() > 0.2 else None,
                last_ip=f"192.168.{random.randint(1,254)}.{random.randint(1,254)}"
            )
            tokens.append(token)

        stats['agent_tokens'] = len(tokens)
        self.stdout.write(self.style.SUCCESS(f'   ✓ 已创建 {len(tokens)} 个Agent Token'))
        return tokens

    def _generate_escalation_policies(self, stats):
        self.stdout.write('⬆️  [15/17] 生成告警升级策略...')

        policy_configs = [
            {
                'name': 'P0致命告警-立即升级至CTO',
                'description': '核心系统中断或数据安全相关P0级告警的紧急升级流程',
                'match_rules': {'severity': 'P0', 'affected_system': ['ins-core', 'db-master', 'payment-gateway']},
                'escalation_steps': [
                    {'level': 1, 'delay_minutes': 0, 'target': 'oncall-l1', 'method': ['phone', 'sms'], 'action': '立即通知一线值班'},
                    {'level': 2, 'delay_minutes': 5, 'target': 'oncall-l2', 'method': ['phone', 'dingtalk'], 'action': '升级至二线技术负责人'},
                    {'level': 3, 'delay_minutes': 15, 'target': 'tech-director', 'method': ['phone', 'email'], 'action': '升级至技术总监'},
                    {'level': 4, 'delay_minutes': 30, 'target': 'cto-office', 'method': ['phone'], 'action': '升级至CTO办公室'},
                ],
            },
            {
                'name': 'P1严重告警-标准升级流程',
                'description': '非核心但影响业务的P1级告警的标准升级路径',
                'match_rules': {'severity': 'P1'},
                'escalation_steps': [
                    {'level': 1, 'delay_minutes': 0, 'target': 'oncall-l1', 'method': ['dingtalk', 'wechat'], 'action': '通知一线值班工程师'},
                    {'level': 2, 'delay_minutes': 15, 'target': 'team-lead', 'method': ['phone', 'dingtalk'], 'action': '升级至团队Leader'},
                    {'level': 3, 'delay_minutes': 45, 'target': 'dept-manager', 'method': ['email', 'phone'], 'action': '升级至部门经理'},
                ],
            },
            {
                'name': '数据安全相关告警-特殊升级通道',
                'description': '涉及客户隐私数据、保单敏感信息的告警采用独立的高优升级通道',
                'match_rules': {'keywords': ['数据泄露', '越权访问', '加密异常', 'ssl', '证书'], 'min_severity': 'P1'},
                'escalation_steps': [
                    {'level': 1, 'delay_minutes': 0, 'target': 'sec-oncall', 'method': ['phone', 'sms'], 'action': '立即通知安全值班'},
                    {'level': 2, 'delay_minutes': 5, 'target': 'ciso', 'method': ['phone', 'email'], 'action': '升级至首席信息安全官'},
                    {'level': 3, 'delay_minutes': 15, 'target': 'legal-compliance', 'method': ['email'], 'action': '通知法务合规部'},
                ],
            },
            {
                'name': '保险业务连续性告警-业务侧升级',
                'description': '影响投保、理赔、保全等核心业务流程的告警需同步升级至业务侧',
                'match_rules': {'business_impact': ['投保失败', '理赔停滞', '无法出单', '支付中断']},
                'escalation_steps': [
                    {'level': 1, 'delay_minutes': 0, 'target': 'ops-team', 'method': ['dingtalk'], 'action': '通知运维团队'},
                    {'level': 2, 'delay_minutes': 10, 'target': 'product-manager', 'method': ['dingtalk', 'phone'], 'action': '同步产品经理'},
                    {'level': 3, 'delay_minutes': 30, 'target': 'business-vp', 'method': ['email', 'phone'], 'action': '升级至业务VP'},
                ],
            },
            {
                'name': '财务结算相关告警-合规升级',
                'description': '涉及保费收取、理赔打款、对账等资金操作的告警需走合规升级流程',
                'match_rules': {'system_domain': ['fin-settle', 'payment-gateway', 'bank-channel'], 'min_severity': 'P1'},
                'escalation_steps': [
                    {'level': 1, 'delay_minutes': 0, 'target': 'finops-team', 'method': ['dingtalk', 'wechat'], 'action': '通知财务运维'},
                    {'level': 2, 'delay_minutes': 15, 'target': 'finance-controller', 'method': ['phone', 'email'], 'action': '升级至财务总监'},
                    {'level': 3, 'delay_minutes': 60, 'target': 'audit-committee', 'method': ['email'], 'action': '抄送内部审计委员会'},
                ],
            },
            {
                'name': '周末/节假日降级响应策略',
                'description': '非工作时间的告警采用降级响应，延长升级间隔',
                'match_rules': {'time_window': ['weekend', 'holiday'], 'max_severity': 'P2'},
                'escalation_steps': [
                    {'level': 1, 'delay_minutes': 0, 'target': 'weekend-oncall', 'method': ['sms', 'phone'], 'action': '短信+电话通知周末值班'},
                    {'level': 2, 'delay_minutes': 60, 'target': 'oncall-l2', 'method': ['phone'], 'action': '1小时后升级至二线'},
                ],
            }
        ]

        policies = []
        for config in policy_configs:
            policy = EscalationPolicy.objects.create(
                name=config['name'],
                description=config.get('description', ''),
                match_rules=config['match_rules'],
                escalation_steps=config['escalation_steps'],
                is_active=random.random() > 0.1
            )
            policies.append(policy)

        stats['escalation_policies'] = len(policies)
        self.stdout.write(self.style.SUCCESS(f'   ✓ 已创建 {len(policies)} 条升级策略'))
        return policies

    def _generate_service_topology(self, servers, stats):
        self.stdout.write('🕸️  [16/17] 生成服务拓扑关系...')

        service_configs = [
            {'name': '保险核心交易服务', 'type': 'application', 'endpoint': '/health/core', 'server_pattern': 'ins-core'},
            {'name': '保单管理服务', 'type': 'application', 'endpoint': '/health/policy', 'server_pattern': 'ins-core'},
            {'name': '理赔处理服务', 'type': 'application', 'endpoint': '/health/claims', 'server_pattern': 'claim-proc'},
            {'name': '客户信息服务', 'type': 'application', 'endpoint': '/health/customer', 'server_pattern': 'cust-svc'},
            {'name': '核保引擎服务', 'type': 'application', 'endpoint': '/health/underwriting', 'server_pattern': 'ins-core'},
            {'name': '风控评分服务', 'type': 'application', 'endpoint': '/health/risk-score', 'server_pattern': 'risk-ctrl'},
            {'name': '反欺诈检测服务', 'type': 'application', 'endpoint': '/health/fraud-detect', 'server_pattern': 'risk-ctrl'},
            {'name': 'MySQL主库', 'type': 'database', 'endpoint': None, 'server_pattern': 'db-master'},
            {'name': 'MySQL从库集群', 'type': 'database', 'endpoint': None, 'server_pattern': 'db-slave'},
            {'name': 'Redis缓存集群', 'type': 'cache', 'endpoint': None, 'server_pattern': 'redis-cluster'},
            {'name': 'Kafka消息队列', 'type': 'queue', 'endpoint': None, 'server_pattern': 'mq-broker'},
            {'name': 'Elasticsearch搜索引擎', 'type': 'storage', 'endpoint': None, 'server_pattern': 'es-node'},
            {'name': 'Nginx API网关', 'type': 'lb', 'endpoint': '/health/nginx', 'server_pattern': 'web-gateway'},
            {'name': '支付网关服务', 'type': 'external', 'endpoint': '/health/payment', 'server_pattern': 'fin-settle'},
            {'name': '银保对接前置服务', 'type': 'external', 'endpoint': '/health/bank-channel', 'server_pattern': 'fin-settle'},
            {'name': '精算计算服务', 'type': 'application', 'endpoint': '/health/actuarial', 'server_pattern': 'risk-ctrl'},
            {'name': '移动端API服务', 'type': 'application', 'endpoint': '/health/mobile-api', 'server_pattern': 'cust-svc'},
            {'name': '代理人展业平台', 'type': 'application', 'endpoint': '/health/agent', 'server_pattern': 'cust-svc'},
            {'name': 'HDFS存储集群', 'type': 'storage', 'endpoint': None, 'server_pattern': 'hadoop'},
        ]

        topology_nodes = []
        server_map = {}
        for svc_config in service_configs:
            matching_servers = [s for s in servers if svc_config['server_pattern'] in s.hostname]
            server = matching_servers[0] if matching_servers else random.choice(servers)

            node = ServiceTopology.objects.create(
                name=svc_config['name'],
                service_type=svc_config['type'],
                server=server,
                health_endpoint=f'http://{server.ip_address}{svc_config["endpoint"]}' if svc_config['endpoint'] else ''
            )
            topology_nodes.append(node)
            server_map[svc_config['name']] = node

        dependencies = [
            ('保险核心交易服务', ['MySQL主库', 'Redis缓存集群', 'Kafka消息队列']),
            ('保单管理服务', ['MySQL主库', 'Elasticsearch搜索引擎']),
            ('理赔处理服务', ['MySQL主库', 'Redis缓存集群', 'Kafka消息队列', '风控评分服务']),
            ('客户信息服务', ['MySQL从库集群', 'Redis缓存集群']),
            ('核保引擎服务', ['风控评分服务', '反欺诈检测服务', 'MySQL主库']),
            ('风控评分服务', ['Elasticsearch搜索引擎', 'HDFS存储集群', 'Redis缓存集群']),
            ('反欺诈检测服务', ['Elasticsearch搜索引擎', 'HDFS存储集群']),
            ('Nginx API网关', ['保险核心交易服务', '保单管理服务', '理赔处理服务', '客户信息服务']),
            ('支付网关服务', ['MySQL主库', '银保对接前置服务']),
            ('银保对接前置服务', ['Kafka消息队列']),
            ('移动端API服务', ['Nginx API网关', '客户信息服务', '保单管理服务']),
            ('代理人展业平台', ['移动端API服务', '核保引擎服务']),
            ('精算计算服务', ['HDFS存储集群', 'MySQL从库集群']),
        ]

        for service_name, dep_names in dependencies:
            if service_name in server_map:
                source_node = server_map[service_name]
                for dep_name in dep_names:
                    if dep_name in server_map and dep_name != service_name:
                        source_node.depends_on.add(server_map[dep_name])

        stats['service_topology'] = len(topology_nodes)
        self.stdout.write(self.style.SUCCESS(f'   ✓ 已创建 {len(topology_nodes)} 个服务拓扑节点及依赖关系'))
        return topology_nodes

    def _generate_dashboards(self, stats):
        self.stdout.write('📊 [17/17] 生成自定义仪表盘...')

        dashboard_configs = [
            {
                'name': '保险核心系统总览面板',
                'config': {
                    'layout': 'grid-4',
                    'widgets': [
                        {'type': 'metric_card', 'title': '实时投保TPS', 'metrics': ['throughput'], 'server_filter': 'ins-core'},
                        {'type': 'metric_card', 'title': '理赔处理队列深度', 'metrics': ['custom_queue_depth'], 'server_filter': 'claim-proc'},
                        {'type': 'time_series', 'title': '核心系统CPU趋势', 'metrics': ['cpu_usage'], 'server_filter': 'ins-core', 'time_range': '1h'},
                        {'type': 'gauge', 'title': '系统健康评分', 'metrics': ['overall_score'], 'server_filter': 'ins-core'},
                        {'type': 'table', 'title': '活跃告警列表', 'source': 'alert_events', 'status': 'firing'},
                        {'type': 'top_n', 'title': '慢响应TOP10接口', 'metrics': ['response_time'], 'n': 10}
                    ],
                    'refresh_interval': 30
                }
            },
            {
                'name': '理赔处理效能监控面板',
                'config': {
                    'layout': 'grid-3',
                    'widgets': [
                        {'type': 'metric_card', 'title': '待处理理赔数', 'metrics': ['queue_depth'], 'server_filter': 'claim-proc'},
                        {'type': 'time_series', '标题': '理赔处理吞吐量', 'metrics': ['throughput'], 'time_range': '6h'},
                        {'type': 'heatmap', 'title': '理赔处理时效热力图', 'dimension': 'processing_time_bucket'},
                        {'type': 'pie_chart', 'title': '理赔类型分布', 'dimension': 'claim_type'}
                    ],
                    'refresh_interval': 60
                }
            },
            {
                'name': '风控数据中心监控面板',
                'config': {
                    'layout': 'grid-4',
                    'widgets': [
                        {'type': 'metric_card', 'title': '实时风险评估QPS', 'metrics': ['throughput'], 'server_filter': 'risk-ctrl'},
                        {'type': 'metric_card', 'title': '模型推理延迟(P99)', 'metrics': ['model_inference_latency'], 'percentile': 99},
                        {'type': 'time_series', 'title': '欺诈检测命中趋势', 'metrics': ['fraud_detection_count'], 'time_range': '24h'},
                        {'type': 'anomaly_chart', 'title': '异常检测事件', 'source': 'anomaly_history', 'severity_filter': 'high'},
                        {'type': 'score_gauge', 'title': '风控模型准确率', 'metric': 'model_accuracy'}
                    ],
                    'refresh_interval': 15
                }
            },
            {
                'name': '基础设施健康大盘',
                'config': {
                    'layout': 'full-width',
                    'widgets': [
                        {'type': 'status_grid', 'title': '服务器状态总览', 'group_by': 'ServerGroup'},
                        {'type': 'health_trend', 'title': '健康评分趋势(30天)', 'metric': 'overall_score', 'time_range': '30d'},
                        {'type': 'alert_summary', 'title': '告警统计摘要', 'group_by': ['severity', 'status']},
                        {'type': 'topology_map', 'title': '服务依赖拓扑图', 'interactive': True}
                    ],
                    'refresh_interval': 60
                }
            },
            {
                'name': '告警运营分析面板',
                'config': {
                    'layout': 'grid-3',
                    'widgets': [
                        {'type': 'bar_chart', 'title': '告警按规则分布', 'dimension': 'rule_name', 'time_range': '7d'},
                        {'type': 'trend_line', 'title': 'MTTR趋势', 'metric': 'mean_time_to_resolve', 'time_range': '30d'},
                        {'type': 'pie_chart', 'title': '告警级别分布', 'dimension': 'severity'},
                        {'type': 'table', 'title': '高频告警TOP20', 'source': 'alert_rules', 'order_by': '-trigger_count'}
                    ],
                    'refresh_interval': 300
                }
            }
        ]

        try:
            user = User.objects.first()
        except Exception:
            user = None

        dashboards = []
        for config in dashboard_configs:
            dashboard = SavedDashboard.objects.create(
                name=config['name'],
                owner=user,
                config=config['config'],
                is_public=random.random() > 0.3,
                share_token=uuid.uuid4().hex[:32] if random.random() > 0.5 else None
            )
            dashboards.append(dashboard)

        stats['dashboards'] = len(dashboards)
        self.stdout.write(self.style.SUCCESS(f'   ✓ 已创建 {len(dashboards)} 个自定义仪表盘'))
        return dashboards

    def _print_summary(self, stats):
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('  ✅ 保险金融行业模拟数据生成完成！'))
        self.stdout.write('=' * 60)

        self.stdout.write('\n📈 数据生成统计摘要:\n')
        self.stdout.write(f'   🖥️  服务器集群:          {stats.get("servers", 0):>6} 台')
        self.stdout.write(f'   ⚠️  预警规则:             {stats.get("alert_rules", 0):>6} 条')
        self.stdout.write(f'   🔍  异常检测算法:         {stats.get("detector_configs", 0):>6} 个')
        self.stdout.write(f'   📈  异常检测记录:         {stats.get("anomaly_histories", 0):>6} 条')
        self.stdout.write(f'   🚨  告警事件:             {stats.get("alert_events", 0):>6} 条')
        self.stdout.write(f'   💚  健康评分记录:         {stats.get("health_scores", 0):>6} 条')
        self.stdout.write(f'   📧  通知发送记录:         {stats.get("notification_logs", 0):>6} 条')
        self.stdout.write(f'   🔇  静默规则:             {stats.get("silence_rules", 0):>6} 条')
        self.stdout.write(f'   📦  告警聚合组:           {stats.get("alert_groups", 0):>6} 个')
        self.stdout.write(f'   🔗  关联规则:             {stats.get("correlation_rules", 0):>6} 条')
        self.stdout.write(f'   🔧  自动修复动作:         {stats.get("remediation_actions", 0):>6} 个')
        self.stdout.write(f'   📋  修复执行记录:         {stats.get("remediation_histories", 0):>6} 条')
        self.stdout.write(f'   📚  运维知识库条目:       {stats.get("runbook_entries", 0):>6} 条')
        self.stdout.write(f'   🤖  Agent Token:          {stats.get("agent_tokens", 0):>6} 个')
        self.stdout.write(f'   ⬆️  升级策略:             {stats.get("escalation_policies", 0):>6} 条')
        self.stdout.write(f'   🕸️  服务拓扑节点:         {stats.get("service_topology", 0):>6} 个')
        self.stdout.write(f'   📊  自定义仪表盘:         {stats.get("dashboards", 0):>6} 个')

        total = sum(stats.values())
        self.stdout.write(f'\n   {"总计":>28} {total:>6} 条记录')

        self.stdout.write('\n💡 使用提示:')
        self.stdout.write('   • 访问 /monitoring/admin/ 查看生成的模拟数据')
        self.stdout.write('   • 使用 --clean 参数可重置测试环境')
        self.stdout.write('   • 使用 --count=100 可生成更大规模数据集')
        self.stdout.write('   • 所有数据均为模拟生成，仅供开发测试使用\n')