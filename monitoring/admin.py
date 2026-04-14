import csv
import io
import logging
from datetime import datetime, timedelta

from django.contrib import admin
from django.http import HttpResponse
from django.utils.html import format_html
from django.utils.timezone import now as tz_now

logger = logging.getLogger(__name__)

from .models import (
    AlertRule, AlertEvent, AlertSilenceRule, NotificationLog, DetectorConfig,
    AnomalyHistory, AlertGroup, AlertCorrelationRule, RemediationAction,
    RemediationHistory, RunbookEntry, AgentToken, EscalationPolicy,
    ServiceTopology, SavedDashboard, HealthScore,
)


# ============================================================
# 选项 D: 数据导出 Mixin - 支持CSV和Excel格式
# ============================================================

class ExportMixin:
    """通用数据导出 Mixin，支持 CSV / Excel 格式"""

    def _get_export_fields(self):
        """获取可导出的字段列表（子类可重写）"""
        return [field.name for field in self.model._meta.fields if field.name != 'id']

    def export_as_csv(self, request, queryset):
        """导出为 CSV 格式"""
        meta = self.model._meta
        field_names = self._get_export_fields()

        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = f'attachment; filename="{meta.verbose_name}_{datetime.now():%Y%m%d_%H%M%S}.csv"'

        writer = csv.writer(response)
        writer.writerow([self.model._meta.get_field(f).verbose_name for f in field_names])

        for obj in queryset:
            row = []
            for field_name in field_names:
                value = getattr(obj, field_name, '')
                if callable(value):
                    value = value()
                if isinstance(value, (dict, list)):
                    value = str(value)
                row.append(str(value).replace('\n', ' ') if value else '')
            writer.writerow(row)

        return response
    export_as_csv.short_description = '📥 导出为 CSV'

    def export_as_excel(self, request, queryset):
        """导出为 Excel 格式 (HTML表格，Excel可直接打开)"""
        meta = self.model._meta
        field_names = self._get_export_fields()

        html_table = f'''
        <html xmlns:o="urn:schemas-microsoft-com:office:office"
              xmlns:x="urn:schemas-microsoft-com:office:excel"
              xmlns="http://www.w3.org/TR/REC-html40">
        <head><meta charset="UTF-8">
        <!--[if gte mso 9]><xml>
        <x:ExcelWorkbook><x:ExcelWorksheets><x:ExcelWorksheet>
            <x:name>{meta.verbose_name}</x:name>
            <x:WorksheetOptions><x:DisplayGridlines/></x:WorksheetOptions>
        </x:ExcelWorksheet></x:ExcelWorksheets></x:ExcelWorkbook>
        </xml><![endif]-->
        </head><body>
        <table border="1"><tr>'''

        for field_name in field_names:
            verbose = self.model._meta.get_field(field_name).verbose_name
            html_table += f'<th>{verbose}</th>'
        html_table += '</tr>'

        for obj in queryset:
            html_table += '<tr>'
            for field_name in field_names:
                value = getattr(obj, field_name, '')
                if isinstance(value, (dict, list)):
                    value = str(value)
                escaped = str(value or '').replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')
                html_table += f'<td>{escaped}</td>'
            html_table += '</tr>'

        html_table += '</table></body></html>'

        response = HttpResponse(html_table, content_type='application/vnd.ms-excel')
        response['Content-Disposition'] = f'attachment; filename="{meta.verbose_name}_{datetime.now():%Y%m%d_%H%M%S}.xls"'
        return response
    export_as_excel.short_description = '📊 导出为 Excel'

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions


# ============================================================
# 选项 C: 自定义 MonitoringAdminSite
# ============================================================

class MonitoringAdminSite(admin.AdminSite):
    """AiOps 监控中心自定义管理站点"""

    site_header = '🤖 AiOps 智能运维监控中心'
    site_title = 'AiOps Admin'
    index_title = '监控运营控制台'
    site_url = '/'

    def get_app_list(self, request, app_label=None):
        """自定义应用排序：monitoring 置顶"""
        app_dict = super().get_app_list(request, app_label)

        if app_dict:
            monitoring_app = next((app for app in app_dict if app.get('app_label') == 'monitoring'), None)
            if monitoring_app:
                app_dict.remove(monitoring_app)
                app_dict.insert(0, monitoring_app)

        return app_dict

    def get_extra_context(self, request):
        """为 AIOps Dashboard 提供统计数据 + AI 智能分析"""
        from django.db.models import Count, Avg, Q, Sum, F
        from django.utils import timezone

        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        hour_ago = now - timedelta(hours=1)

        stats = {}

        try:
            from cmdb.models import Server
            stats['total_servers'] = Server.objects.count()
            stats['active_agents'] = Server.objects.filter(
                agent_status='online', is_monitored=True
            ).count() if hasattr(Server, 'agent_status') else 0
        except Exception:
            pass

        try:
            stats['firing_alerts'] = AlertEvent.objects.filter(status='firing').count()
            stats['enabled_rules'] = AlertRule.objects.filter(status='enabled').count()
            stats['today_alerts'] = AlertEvent.objects.filter(
                fired_at__gte=today_start
            ).count()
            stats['hour_alerts'] = AlertEvent.objects.filter(
                fired_at__gte=hour_ago
            ).count()
        except Exception:
            pass

        try:
            health_scores = HealthScore.objects.all().order_by('-scored_at')
            if health_scores.exists():
                avg_score = health_scores.aggregate(avg=Avg('overall_score'))['avg']
                stats['avg_health_score'] = f"{avg_score:.0f}" if avg_score else '-'
        except Exception:
            pass

        try:
            remediation_total = RemediationHistory.objects.count()
            remediation_success = RemediationHistory.objects.filter(
                status='success'
            ).count()
            auto_resolved = RemediationHistory.objects.filter(
                status='success'
            ).count()
            stats['remediation_success_rate'] = (
                round(remediation_success / remediation_total * 100) 
                if remediation_total > 0 else 0
            )
            stats['auto_heal_count'] = auto_resolved
            stats['total_remediations'] = remediation_total
        except Exception:
            pass

        try:
            stats['total_runbook_entries'] = RunbookEntry.objects.count()
        except Exception:
            pass

        channels = []
        try:
            from .notification.channel_manager import channel_manager
            channels = list(channel_manager.channels.keys()) or []
        except Exception:
            pass
        stats['active_channels'] = ', '.join(channels[:3]) + ('...' if len(channels) > 3 else '') if channels else '-'

        # ===== AIOps 智能数据 =====
        
        # AI 诊断统计
        ai_diagnosis_data = []
        try:
            from monitoring.models import AnomalyHistory
            recent_ai = AnomalyHistory.objects.filter(
                ai_analyzed_at__isnull=False
            ).select_related('alert_event', 'alert_event__rule').order_by('-ai_analyzed_at')[:6]
            
            ai_stats = AnomalyHistory.objects.filter(ai_analyzed_at__isnull=False).aggregate(
                total=Count('id'),
                avg_confidence=Avg('ai_confidence'),
                high_conf=Count('id', filter=Q(ai_confidence__gte=0.8)),
            )
            
            for item in recent_ai:
                diagnosis_detail = (item.alert_event.detail or {}).get('ai_diagnosis', {}) if item.alert_event else {}
                ai_diagnosis_data.append({
                    'event_id': item.alert_event_id,
                    'server': item.alert_event.server.hostname if item.alert_event and item.alert_event.server else '-',
                    'metric': item.alert_event.metric_name if item.alert_event else '-',
                    'analysis': diagnosis_detail.get('analysis', item.ai_diagnosis or '分析中...')[:120],
                    'confidence': round(item.ai_confidence, 2) if item.ai_confidence else 0,
                    'root_cause': diagnosis_detail.get('root_cause_category', '-'),
                    'urgency': diagnosis_detail.get('urgency', '-'),
                    'analyzed_at': item.ai_analyzed_at,
                })
            
            stats['ai_total_diagnoses'] = ai_stats['total']
            stats['ai_avg_confidence'] = round(ai_stats['avg_confidence'], 2) if ai_stats['avg_confidence'] else 0
            stats['ai_high_conf_count'] = ai_stats['high_conf']
        except Exception as e:
            logger.warning(f"[Dashboard] AI诊断数据获取失败: {e}")

        # 异常检测算法分布
        anomaly_method_stats = []
        try:
            from monitoring.models import AnomalyHistory as AH
            method_counts = AH.objects.values('detection_method').annotate(
                count=Count('id')
            ).order_by('-count')[:8]
            
            method_icons = {
                'zscore': ('📊', 'Z-Score检测'), 'iqr': ('📈', 'IQR四分位'),
                'moving_avg': ('📉', '移动平均'), 'rate_of_change': ('⚡', '变化率'),
                'composite': ('🧠', '复合投票'), 'threshold': ('🎯', '阈值检测'),
                'baseline': ('📐', '动态基线'), 'trend': ('📊', '趋势检测'),
            }
            total_anomalies = sum(m['count'] for m in method_counts)
            
            for mc in method_counts:
                method = mc['detection_method']
                icon, label = method_icons.get(method, ('🔍', method))
                pct = round(mc['count'] / total_anomalies * 100) if total_anomalies > 0 else 0
                anomaly_method_stats.append({
                    'method': method, 'icon': icon, 'label': label,
                    'count': mc['count'], 'percentage': pct,
                })
            
            stats['total_anomalies'] = total_anomalies
        except Exception as e:
            logger.warning(f"[Dashboard] 异常算法统计失败: {e}")

        # 告警关联聚类（最近活跃）
        alert_clusters = []
        try:
            from monitoring.correlation.correlator import Correlator
            clusters = Correlator.find_active_clusters()
            for cluster in clusters[:5]:
                servers = list(set(c.server.hostname for c in cluster if c.server))
                metrics = list(set(c.metric_name for c in cluster))
                severities = [c.severity for c in cluster]
                alert_clusters.append({
                    'size': len(cluster),
                    'servers': ', '.join(servers[:3]) + ('...' if len(servers) > 3 else ''),
                    'metrics': ', '.join(metrics[:3]),
                    'max_severity': min(severities),
                    'top_alert': cluster[0].rule.name if cluster[0].rule else '-',
                    'time': cluster[0].fired_at.strftime('%H:%M:%S') if cluster[0].fired_at else '-',
                })
            stats['active_clusters'] = len(clusters)
        except Exception as e:
            logger.warning(f"[Dashboard] 告警聚类失败: {e}")

        # 根因分类统计
        root_cause_distribution = []
        try:
            rc_categories = {
                '资源不足': {'icon': '💾', 'color': '#ff4d4f', 'key': 'resource_exhaustion'},
                '配置错误': {'icon': '⚙️', 'color': '#fa8c16', 'key': 'config_error'},
                '外部攻击': {'icon': '🛡️', 'color': '#722ed1', 'key': 'security'},
                '正常波动': {'icon': '🌊', 'color': '#52c41a', 'key': 'noise'},
                '网络问题': {'icon': '🌐', 'color': '#1890ff', 'key': 'network'},
                '其他': {'icon': '❓', 'color': '#8c8c8c', 'key': 'other'},
            }
            
            events_with_ai = [a for a in AlertEvent.objects.filter(
                detail__ai_diagnosis__isnull=False
            )[:50] if a.detail and isinstance(a.detail, dict)]
            
            rc_counts = {}
            for event in events_with_ai:
                rc = (event.detail.get('ai_diagnosis') or {}).get('root_cause_category', 'other')
                rc_key = next((k for k, v in rc_categories.items() if k in str(rc)), '其他')
                rc_counts[rc_key] = rc_counts.get(rc_key, 0) + 1
            
            total_rc = sum(rc_counts.values())
            for cat_name, info in rc_categories.items():
                cnt = rc_counts.get(cat_name, 0)
                root_cause_distribution.append({
                    'name': cat_name, 'icon': info['icon'], 'color': info['color'],
                    'count': cnt, 'pct': round(cnt / total_rc * 100) if total_rc > 0 else 0,
                })
            
            stats['ai_root_cause_total'] = total_rc
        except Exception as e:
            logger.warning(f"[Dashboard] 根因统计失败: {e}")

        # 自动修复时间线
        remediation_timeline = []
        try:
            recent_remediations = RemediationHistory.objects.select_related(
                'action', 'alert_event', 'alert_event__rule'
            ).order_by('-started_at')[:5]
            
            for rh in recent_remediations:
                duration = ''
                if rh.started_at and rh.finished_at:
                    secs = (rh.finished_at - rh.started_at).total_seconds()
                    if secs < 60:
                        duration = f'{secs:.0f}秒'
                    else:
                        duration = f'{secs/60:.1f}分钟'
                
                status_config = {
                    'success': ('✅', '#52c41a'), 'failed': ('❌', '#ff4d4f'),
                    'running': ('🔄', '#1890ff'), 'pending': ('⏳', '#faad14'),
                    'needs_confirmation': ('🔒', '#722ed1'),
                }
                s_icon, s_color = status_config.get(rh.status, ('?', '#8c8c8c'))
                
                remediation_timeline.append({
                    'id': rh.id,
                    'action_name': rh.action.name if rh.action else '-',
                    'status_icon': s_icon, 'status_color': s_color,
                    'status': rh.status,
                    'server': rh.alert_event.server.hostname if rh.alert_event and rh.alert_event.server else '-',
                    'alert_rule': rh.alert_event.rule.name if rh.alert_event and rh.alert_event.rule else '-',
                    'duration': duration,
                    'started_at': rh.started_at,
                    'is_auto': not rh.action.is_dangerous if rh.action else False,
                })
        except Exception as e:
            logger.warning(f"[Dashboard] 修复时间线失败: {e}")

        # 知识库智能推荐
        runbook_recommendations = []
        try:
            from monitoring.runbook.recommender import RunbookRecommender
            latest_firing = AlertEvent.objects.filter(status='firing').select_related('rule', 'server').first()
            if latest_firing:
                recs = RunbookRecommender.recommend_for_alert(latest_firing, limit=4)
                runbook_recommendations = recs
                stats['runbook_for_alert'] = {
                    'metric': latest_firing.metric_name,
                    'severity': latest_firing.severity,
                    'server': latest_firing.server.hostname if latest_firing.server else '-',
                }
        except Exception as e:
            logger.warning(f"[Dashboard] 知识库推荐失败: {e}")

        # 趋势预测（基于历史数据简单预测）
        trend_data = []
        try:
            for hours_ago in range(12, -1, -1):
                t = now - timedelta(hours=hours_ago)
                t_start = t.replace(minute=0, second=0, microsecond=0)
                t_end = t_start + timedelta(hours=1)
                cnt = AlertEvent.objects.filter(
                    fired_at__gte=t_start, fired_at__lt=t_end
                ).count()
                trend_data.append({
                    'time': t_start.strftime('%H:00'),
                    'alerts': cnt,
                })
        except Exception:
            pass

        recent_alerts = list(AlertEvent.objects.select_related('rule', 'server').order_by('-fired_at')[:10])
        health_overview = list(HealthScore.objects.select_related('server').order_by('-scored_at')[:8])

        context = {
            'stats': stats,
            'recent_alerts': recent_alerts,
            'health_overview': health_overview,
            'django_version': __import__('django').VERSION[:2],
            # AIOps 数据
            'ai_diagnosis_data': ai_diagnosis_data,
            'anomaly_method_stats': anomaly_method_stats,
            'alert_clusters': alert_clusters,
            'root_cause_dist': root_cause_distribution,
            'remediation_timeline': remediation_timeline,
            'runbook_recommendations': runbook_recommendations,
            'trend_data': trend_data,
        }

        try:
            from django.db import connection
            context['db_engine'] = connection.vendor.title()
        except Exception:
            pass

        return context

    def each_context(self, request):
        """将 Dashboard 上下文注入到每个页面"""
        context = super().each_context(request)
        extra_context = self.get_extra_context(request)
        context.update(extra_context)
        return context


monitoring_admin_site = MonitoringAdminSite(name='monitoring_admin')


# ============================================================
# 预警规则 Admin (含导出)
# ============================================================

@admin.register(AlertRule, site=monitoring_admin_site)
class AlertRuleAdmin(ExportMixin, admin.ModelAdmin):
    list_display = ['name', 'rule_type', 'severity_badge', 'status',
                    'metric_name', 'trigger_count', 'last_triggered_at']
    list_filter = ['status', 'severity', 'rule_type', 'metric_name']
    search_fields = ['name', 'description']
    readonly_fields = ['trigger_count', 'last_triggered_at', 'created_at', 'updated_at']
    actions = ['export_as_csv', 'export_as_excel']

    fieldsets = (
        ('基本信息', {'fields': ('name','description','rule_type','severity','status')}),
        ('目标配置', {'fields': ('target_all','metric_name','condition_config')}),
        ('评估参数', {'fields': ('evaluate_interval','lookback_window','cooldown_seconds','max_alerts_per_hour')}),
        ('通知配置', {'fields': ('notify_channels','notify_template')}),
        ('元数据', {'fields': ('created_by','trigger_count','last_triggered_at','created_at','updated_at'),
                   'classes': ('collapse',)}),
    )

    def severity_badge(self, obj):
        colors = {'P0':'#ff4d4f','P1':'#fa8c16','P2':'#faad14','P3':'#52c41a'}
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 10px;border-radius:10px;font-size:11px;font-weight:bold">{}</span>',
            colors.get(obj.severity,'#1890ff'), obj.severity
        )
    severity_badge.short_description = '级别'
    severity_badge.admin_order_field = 'severity'


# ============================================================
# 告警事件 Admin (含导出 + 内联修复记录)
# ============================================================

class RemediationHistoryInline(admin.TabularInline):
    model = RemediationHistory
    extra = 0
    readonly_fields = ['action', 'status', 'started_at', 'finished_at', 'output_short']
    can_delete = False

    def output_short(self, instance):
        return (instance.output or '')[:100] + '...' if len(instance.output or '') > 100 else (instance.output or '-')
    output_short.short_description = '执行输出'
    output_short.allow_tags = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(AlertEvent, site=monitoring_admin_site)
class AlertEventAdmin(ExportMixin, admin.ModelAdmin):
    list_display = ['id', 'rule_link', 'server_link', 'severity_badge',
                    'status_tag', 'current_value', 'duration_human', 'fired_at']
    list_filter = ['status', 'severity', 'rule__rule_type', 'metric_name']
    search_fields = ['message', 'server__hostname', 'rule__name']
    readonly_fields = ['fired_at', 'resolved_at', 'notification_log', 'detail_json']
    date_hierarchy = 'fired_at'
    actions = ['export_as_csv', 'export_as_excel', 'batch_acknowledge', 'batch_resolve']
    inlines = [RemediationHistoryInline]

    def has_add_permission(self, request):
        return False

    def rule_link(self, obj):
        url = f'/monitoring/admin/monitoring/alertrule/{obj.rule_id}/change/'
        return format_html('<a href="{}">{}</a>', url, obj.rule.name)
    rule_link.short_description = '规则'
    rule_link.admin_order_field = 'rule__name'

    def server_link(self, obj):
        if obj.server:
            url = f'/admin/cmdb/server/{obj.server_id}/change/'
            return format_html('<a href="{}">{}</a>', url, obj.server.hostname)
        return '-'
    server_link.short_description = '服务器'
    server_link.admin_order_field = 'server__hostname'

    def severity_badge(self, obj):
        colors = {'P0':'#ff4d4f','P1':'#fa8c16','P2':'#faad14','P3':'#52c41a'}
        labels = {'P0':'致命','P1':'严重','P2':'警告','P3':'提示'}
        return format_html(
            '<span style="color:{};font-weight:bold">{}</span>',
            colors.get(obj.severity,'#1890ff'), labels.get(obj.severity, obj.severity)
        )
    severity_badge.short_description = '级别'

    def status_tag(self, obj):
        status_config = {
            'firing': ('red', '🔴 触发中'),
            'resolved': ('green', '✅ 已恢复'),
            'acknowledged': ('blue', '👁 已确认'),
            'silenced': ('gray', '🔇 已静默'),
        }
        color, label = status_config.get(obj.status, ('gray', obj.status))
        return format_html('<span style="color:{}">{}</span>', color, label)
    status_tag.short_description = '状态'

    def duration_human(self, obj):
        duration = obj.duration
        if duration is None:
            return '-'
        hours = int(duration // 3600)
        minutes = int((duration % 3600) // 60)
        if hours > 0:
            return f'{hours}h {minutes}m'
        return f'{minutes}m'
    duration_human.short_description = '持续'

    def detail_json(self, obj):
        import json
        detail = obj.detail or {}
        return format_html('<pre style="max-height:300px;overflow:auto;background:#f5f5f5;padding:10px;border-radius:4px">{}</pre>',
                          json.dumps(detail, indent=2, ensure_ascii=False))
    detail_json.short_description = '详细信息'

    def batch_acknowledge(self, request, queryset):
        updated = queryset.filter(status='firing').update(
            status='acknowledged',
            acknowledged_at=tz_now(),
            acknowledged_by=request.user
        )
        self.message_user(request, f'✅ 已成功确认 {updated} 条告警事件')
    batch_acknowledge.short_description = '👁 批量确认告警'

    def batch_resolve(self, request, queryset):
        from django.utils import timezone
        updated = queryset.exclude(status='resolved').update(
            status='resolved',
            resolved_at=timezone.now()
        )
        self.message_user(request, f'✅ 已成功解决 {updated} 条告警事件')
    batch_resolve.short_description = '✅ 批量解决告警'


# ============================================================
# 其他核心模型 Admin (含导出)
# ============================================================

@admin.register(AlertSilenceRule, site=monitoring_admin_site)
class AlertSilenceRuleAdmin(admin.ModelAdmin):
    list_display = ['name', 'match_severity_display', 'match_server', 'is_active',
                    'time_range', 'comment_short']
    list_filter = ['is_active']
    list_editable = ['is_active']
    search_fields = ['name', 'comment']

    def match_severity_display(self, obj):
        return obj.match_severity or '全部'
    match_severity_display.short_description = '匹配级别'

    def time_range(self, obj):
        return f"{obj.start_time:%m-%d %H:%M} ~ {obj.end_time:%m-%d %H:%M}"
    time_range.short_description = '时间范围'

    def comment_short(self, obj):
        return (obj.comment or '')[:50]
    comment_short.short_description = '备注'


@admin.register(NotificationLog, site=monitoring_admin_site)
class NotificationLogAdmin(ExportMixin, admin.ModelAdmin):
    list_display = ['channel_badge', 'status_icon', 'alert_event_link',
                    'recipient_short', 'retry_count', 'sent_at']
    list_filter = ['channel', 'status']
    actions = ['export_as_csv', 'export_as_excel']
    date_hierarchy = 'sent_at'

    def has_add_permission(self, request):
        return False

    def channel_badge(self, obj):
        icons = {
            'dingtalk':'💬 钉钉', 'wechat':'💚 企微', 'email':'📧 邮件',
            'slack':'#️⃣ Slack', 'webhook': '🔗 Webhook'
        }
        return icons.get(obj.channel, obj.channel)
    channel_badge.short_description = '渠道'

    def status_icon(self, obj):
        config = {'sent':'✅','failed':'❌','retrying':'🔄'}
        return config.get(obj.status, obj.status)
    status_icon.short_description = '状态'

    def alert_event_link(self, obj):
        if obj.alert_event_id:
            return format_html('<a href="/monitoring/admin/monitoring/alertevent/{}/change/">#{}</a>',
                              obj.alert_event_id, obj.alert_event_id)
        return '-'
    alert_event_link.short_description = '告警ID'

    def recipient_short(self, obj):
        rec = obj.recipient or {}
        return str(rec)[:50]
    recipient_short.short_description = '接收者'


@admin.register(DetectorConfig, site=monitoring_admin_site)
class DetectorConfigAdmin(admin.ModelAdmin):
    list_display = ['detector_name', 'is_enabled', 'params_preview', 'updated_by_link', 'updated_at']
    list_editable = ['is_enabled']
    list_filter = ['is_enabled', 'detector_name']
    actions = ['copy_config']

    fieldsets = (
        ('基本信息', {'fields': ('detector_name', 'is_enabled', 'description', 'updated_by')}),
        ('参数配置', {
            'fields': ('params',),
            'classes': ('collapse',),
            'description': '''
            <div style="background:#e6f7ff;padding:12px;border-radius:6px;margin-bottom:10px">
            <b style="color:#1890ff">📖 各检测器参数说明</b><br><br>
            <table style="width:100%;border-collapse:collapse">
            <tr><td style="padding:4px;border-bottom:1px solid #ddd"><b>Z-Score</b></td>
                <td style="padding:4px;border-bottom:1px solid #ddd"><code>{"threshold": 2.5}</code></td>
                <td style="padding:4px;border-bottom:1px solid #ddd">阈值(标准差倍数)</td></tr>
            <tr><td style="padding:4px;border-bottom:1px solid #ddd"><b>IQR</b></td>
                <td style="padding:4px;border-bottom:1px solid #ddd"><code>{"k": 1.5}</code></td>
                <td style="padding:4px;border-bottom:1px solid #ddd">四分位距倍数</td></tr>
            <tr><td style="padding:4px;border-bottom:1px solid #ddd"><b>移动平均</b></td>
                <td style="padding:4px;border-bottom:1px solid #ddd"><code>{"window": 10, "factor": 2.0}</code></td>
                <td style="padding:4px;border-bottom:1px solid #ddd">窗口大小 + 偏差倍数</td></tr>
            <tr><td style="padding:4px;border-bottom:1px solid #ddd"><b>变化率</b></td>
                <td style="padding:4px;border-bottom:1px solid #ddd"><code>{"threshold": 50.0}</code></td>
                <td style="padding:4px;border-bottom:1px solid #ddd">变化百分比阈值</td></tr>
            <tr><td style="padding:4px"><b>复合投票</b></td>
                <td style="padding:4px"><code>{"vote_thr": 0.6}</code></td>
                <td style="padding:4px">投票通过阈值</td></tr>
            </table></div>
            ''',
        }),
    )

    def params_preview(self, obj):
        params = obj.params or {}
        items = [f'{k}={v}' for k, v in params.items()]
        return ', '.join(items[:3]) + ('...' if len(items) > 3 else '')
    params_preview.short_description = '参数预览'

    def updated_by_link(self, obj):
        if obj.updated_by:
            return format_html('<a href="/admin/auth/user/{}/change/">{}</a>',
                              obj.updated_by_id, obj.updated_by.username)
        return '-'
    updated_by_link.short_description = '更新者'

    def copy_config(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, '❌ 请选择一条记录进行复制', level='error')
            return
        obj = queryset.first()
        DetectorConfig.objects.create(
            detector_name=obj.detector_name,
            params=obj.params.copy(),
            description=f"[复制自] {obj.description or ''}",
            updated_by=request.user
        )
        self.message_user(request, f'✅ 已复制检测器配置: {obj.detector_name}')
    copy_config.short_description = '📋 复制选中配置'


@admin.register(AnomalyHistory, site=monitoring_admin_site)
class AnomalyHistoryAdmin(ExportMixin, admin.ModelAdmin):
    list_display = ['server_link', 'metric_name', 'severity_badge', 'anomaly_score_bar',
                    'method_used', 'current_value', 'detected_at', 'ai_status']
    list_filter = ['severity', 'metric_name', 'method_used']
    search_fields = ['server__hostname', 'metric_name']
    date_hierarchy = 'detected_at'
    actions = ['export_as_csv', 'export_as_excel', 'batch_request_ai_analysis']

    def has_add_permission(self, request):
        return False

    def server_link(self, obj):
        if obj.server:
            return format_html('<a href="/admin/cmdb/server/{}/change/">{}</a>',
                              obj.server_id, obj.server.hostname)
        return '-'
    server_link.short_description = '服务器'

    def severity_badge(self, obj):
        config = {
            'high': ('#ff4d4f', '🔴 高度异常'),
            'medium': ('#faad14', '🟡 中度异常'),
            'low': ('#1890ff', '🔵 轻度异常'),
        }
        color, label = config.get(obj.severity, ('#999', obj.severity))
        return format_html('<span style="color:{};font-weight:bold">{}</span>', color, label)
    severity_badge.short_description = '程度'

    def anomaly_score_bar(self, obj):
        score = obj.anomaly_score or 0
        width = min(score * 100, 100)
        color = '#ff4d4f' if score > 0.8 else '#faad14' if score > 0.5 else '#52c41a'
        return format_html('''
            <div style="width:80px;background:#f0f0f0;border-radius:4px;position:relative;height:16px">
            <div style="width:{}%;background:{};border-radius:4px;height:100%"></div>
            <span style="position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);font-size:10px">{:.2f}</span>
            </div>
        ''', width, color, score)
    anomaly_score_bar.short_description = '异常分数'
    anomaly_score_bar.admin_order_field = 'anomaly_score'

    def ai_status(self, obj):
        if obj.ai_diagnosis:
            conf = obj.ai_confidence or 0
            return format_html('<span title="{}">🤖 {:.0%}</span>',
                              obj.ai_diagnosis[:50], conf)
        return format_html('<span style="color:#999">⬜ 未分析</span>')
    ai_status.short_description = 'AI诊断'

    def batch_request_ai_analysis(self, request, queryset):
        unanalyzed = queryset.filter(ai_diagnosis='')
        count = unanalyzed.count()
        if count == 0:
            self.message_user(request, 'ℹ️ 选中的记录已全部完成AI分析')
            return
        from monitoring.ai_callback import anomaly_ai_callback_task
        for obj in unanalyzed[:20]:
            try:
                anomaly_ai_callback_task.delay(
                    event_id=obj.alert_event_id,
                    server_id=obj.server_id,
                    metric_name=obj.metric_name
                )
            except Exception:
                pass
        self.message_user(request, f'🤖 已提交 {min(count, 20)} 条记录的AI分析任务')
    batch_request_ai_analysis.short_description = '🤖 批量请求AI分析'


@admin.register(AlertGroup, site=monitoring_admin_site)
class AlertGroupAdmin(ExportMixin, admin.ModelAdmin):
    list_display = ['name_truncated', 'fingerprint_code', 'status_tag', 'severity_badge',
                    'alert_count_badge', 'time_span', 'assigned_to_link']
    list_filter = ['status', 'severity']
    search_fields = ['name', 'fingerprint']
    readonly_fields = ['first_fired_at', 'last_fired_at', 'alert_count', 'resolved_at']
    actions = ['export_as_csv', 'export_as_excel', 'batch_assign_to_me']

    def name_truncated(self, obj):
        name = obj.name or ''
        return name[:60] + '...' if len(name) > 60 else name
    name_truncated.short_description = '聚合组名'

    def fingerprint_code(self, obj):
        fp = obj.fingerprint or ''
        return format_html('<code style="font-size:11px;color:#666">{}</code>', fp[:16])
    fingerprint_code.short_description = '指纹'

    def status_tag(self, obj):
        config = {'firing':('🔴 触发中','red'), 'resolved':('✅ 已解决','green')}
        label, color = config.get(obj.status, (obj.status, 'gray'))
        return format_html('<span style="color:{};font-weight:bold">{}</span>', color, label)
    status_tag.short_description = '状态'

    def severity_badge(self, obj):
        colors = {'P0':'#ff4d4f','P1':'#fa8c16','P2':'#faad14','P3':'#52c41a'}
        return format_html('<span style="color:{};font-weight:bold">{}</span>',
                           colors.get(obj.severity,'#1890ff'), obj.severity)
    severity_badge.short_description = '级别'

    def alert_count_badge(self, obj):
        count = obj.alert_count or 0
        color = '#ff4d4f' if count >= 20 else '#faad14' if count >= 5 else '#52c41a'
        return format_html('<span style="background:{};color:#fff;padding:2px 8px;border-radius:10px;font-weight:bold">{}</span>',
                           color, count)
    alert_count_badge.short_description = '告警数'

    def time_span(self, obj):
        if obj.resolved_at and obj.first_fired_at:
            delta = obj.resolved_at - obj.first_fired_at
            return f'{int(delta.total_seconds() / 3600)}h {(int(delta.total_seconds() / 60)) % 60}m'
        return '-'
    time_span.short_description = '持续时间'

    def assigned_to_link(self, obj):
        if obj.assigned_to:
            return format_html('<a href="/admin/auth/user/{}/change/">{}</a>',
                              obj.assigned_to_id, obj.assigned_to.username)
        return '-'
    assigned_to_link.short_description = '负责人'

    def batch_assign_to_me(self, request, queryset):
        updated = queryset.update(assigned_to=request.user)
        self.message_user(request, f'✅ 已将 {updated} 个聚合组分配给您')
    batch_assign_to_me.short_description = '👤 分配给我'


@admin.register(AlertCorrelationRule, site=monitoring_admin_site)
class AlertCorrelationRuleAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'confidence_weight', 'root_cause_hint', 'patterns_preview']
    list_editable = ['is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'root_cause_hint', 'suggested_action']

    def root_cause_hint(self, obj):
        return (obj.root_cause_hint or '')[:60]
    root_cause_hint.short_description = '根因提示'

    def patterns_preview(self, obj):
        patterns = obj.trigger_patterns or {}
        return format_html('<code style="font-size:11px">{}</code>', str(patterns)[:40])
    patterns_preview.short_description = '触发模式'


@admin.register(RemediationAction, site=monitoring_admin_site)
class RemediationActionAdmin(admin.ModelAdmin):
    list_display = ['name', 'action_type_badge', 'severity_filter',
                    'dangerous_tag', 'is_active', 'timeout_format']
    list_filter = ['action_type', 'is_active', 'is_dangerous']
    list_editable = ['is_active']
    search_fields = ['name', 'target_command']

    fieldsets = (
        ('基本信息', {'fields': ('name','action_type','is_dangerous','is_active','severity_filter')}),
        ('执行配置', {
            'fields': ('target_command','timeout_seconds','max_retries'),
            'description': '<div style="color:#fa8c16">⚠️ 危险操作将在执行前要求人工确认</div>' if True else '',
        }),
    )

    def action_type_badge(self, obj):
        icons = {
            'script':'📜 脚本', 'service_restart':'🔄 重启', 'disk_cleanup':'🧹 清理',
            'scale_out':'📈 扩容', 'webhook': '🔗 Webhook', 'custom':'⚙️ 自定义'
        }
        return icons.get(obj.action_type, obj.action_type)
    action_type_badge.short_description = '动作类型'

    def dangerous_tag(self, obj):
        if obj.is_dangerous:
            return format_html('<span style="color:#ff4d4f;font-weight:bold">☠️ 危险</span>')
        return format_html('<span style="color:#52c41a">✅ 安全</span>')
    dangerous_tag.short_description = '安全等级'

    def timeout_format(self, obj):
        mins = obj.timeout_seconds // 60
        return f'{mins}分钟' if mins >= 1 else f'{obj.timeout_seconds}秒'
    timeout_format.short_description = '超时'


@admin.register(RemediationHistory, site=monitoring_admin_site)
class RemediationHistoryAdmin(ExportMixin, admin.ModelAdmin):
    list_display = ['id', 'alert_event_link', 'action_link', 'status_badge',
                    'duration', 'error_summary', 'started_at']
    list_filter = ['status', 'action__action_type']
    actions = ['export_as_csv', 'export_as_excel']
    date_hierarchy = 'started_at'
    readonly_fields = ['started_at', 'finished_at', 'output', 'error_message']

    def has_add_permission(self, request):
        return False

    def alert_event_link(self, obj):
        return format_html('<a href="/monitoring/admin/monitoring/alertevent/{}/change/">#{}</a>',
                          obj.alert_event_id, obj.alert_event_id)
    alert_event_link.short_description = '告警'

    def action_link(self, obj):
        return format_html('<a href="/monitoring/admin/monitoring/remediationaction/{}/change/">{}</a>',
                          obj.action_id, obj.action.name)
    action_link.short_description = '动作'

    def status_badge(self, obj):
        config = {
            'pending':('⏳ 待执行','#999'), 'running':('🔄 执行中','#1890ff'),
            'success':('✅ 成功','#52c41a'), 'failed':('❌ 失败','#ff4d4f'),
            'timeout':('⏰ 超时','#fa8c16'), 'cancelled':('🚫 取消','#999')
        }
        icon, color = config.get(obj.status, (obj.status, '#999'))
        return format_html('<span style="color:{};font-weight:bold">{}</span>', color, icon)
    status_badge.short_description = '状态'

    def duration(self, obj):
        if obj.started_at and obj.finished_at:
            delta = obj.finished_at - obj.started_at
            secs = delta.total_seconds()
            return f'{int(secs)}s' if secs < 60 else f'{secs/60:.1f}m'
        return '-'
    duration.short_description = '耗时'

    def error_summary(self, obj):
        err = obj.error_message or ''
        return err[:60] + '...' if len(err) > 60 else err
    error_summary.short_description = '错误信息'


@admin.register(RunbookEntry, site=monitoring_admin_site)
class RunbookEntryAdmin(ExportMixin, admin.ModelAdmin):
    list_display = ['title_truncated', 'category_badge', 'effectiveness_star',
                    'usage_count', 'is_published', 'tags_list', 'created_at']
    list_filter = ['category', 'is_published']
    list_editable = ['is_published']
    search_fields = ['title', 'solution', 'tags']
    actions = ['export_as_csv', 'export_as_excel', 'mark_as_featured']

    def title_truncated(self, obj):
        return obj.title[:60] + '...' if len(obj.title) > 60 else obj.title
    title_truncated.short_description = '标题'

    def category_badge(self, obj):
        colors = {
            'network':'#1890ff','storage':'#722ed1','memory':'#13c2c2',
            'cpu':'#fa8c16','database':'#eb2f96','application':'#52c41a',
            'security':'#ff4d4f','general':'#999'
        }
        return format_html('<span style="background:{};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px">{}</span>',
                           colors.get(obj.category,'#999'), obj.get_category_display())
    category_badge.short_description = '分类'

    def effectiveness_star(self, obj):
        score = obj.effectiveness_score or 0
        filled = round(score * 5)
        empty = 5 - filled
        return format_html('{}{}', '★' * filled, '☆' * empty)
    effectiveness_star.short_description = '有效评分'
    effectiveness_star.admin_order_field = 'effectiveness_score'

    def tags_list(self, obj):
        tags = obj.tag_list
        if not tags:
            return '-'
        return format_html('{}'.format(
            ' '.join([f'<span style="background:#f0f0f0;padding:1px 6px;border-radius:3px;font-size:11px;margin:1px">{t}</span>' for t in tags[:4]])
        ))
    tags_list.short_description = '标签'
    tags_list.allow_tags = True

    def mark_as_featured(self, request, queryset):
        updated = queryset.update(is_published=True, effectiveness_score=1.0)
        self.message_user(request, f'⭐ 已将 {updated} 条知识库条目标记为精选')
    mark_as_featured.short_description = '⭐ 标记为精选'


@admin.register(AgentToken, site=monitoring_admin_site)
class AgentTokenAdmin(admin.ModelAdmin):
    list_display = ['name', 'server_link', 'token_mask', 'is_alive',
                    'last_seen_ago', 'created_at']
    list_filter = ['is_active']
    readonly_fields = ['token', 'created_at', 'last_seen_at']
    search_fields = ['name', 'server__hostname']
    actions = ['regenerate_tokens', 'deactivate_stale']

    def server_link(self, obj):
        if obj.server:
            return format_html('<a href="/admin/cmdb/server/{}/change/">{}</a>',
                              obj.server_id, obj.server.hostname)
        return '-'
    server_link.short_description = '服务器'

    def token_mask(self, obj):
        token = obj.token or ''
        visible = token[:8]
        masked = '*' * 16
        return format_html('<code style="font-size:11px;letter-spacing:1px">{}</code>', visible + masked)
    token_mask.short_description = 'Token'

    def is_alive(self, obj):
        if not obj.last_seen_at:
            return format_html('<span style="color:#999">从未连接</span>')
        if obj.last_seen_at and (tz_now() - obj.last_seen_at) < timedelta(minutes=5):
            return format_html('<span style="color:#52c41a;font-weight:bold">● 在线</span>')
        return format_html('<span style="color:#ff4d4f">● 离线</span>')
    is_alive.short_description = '状态'

    def last_seen_ago(self, obj):
        if not obj.last_seen_at:
            return '-'
        delta = tz_now() - obj.last_seen_at
        minutes = int(delta.total_seconds() / 60)
        if minutes < 60:
            return f'{minutes}分钟前'
        hours = minutes // 60
        return f'{hours}小时{minutes % 60}分钟前'
    last_seen_ago.short_description = '最后活跃'

    def regenerate_tokens(self, request, queryset):
        import secrets
        count = 0
        for obj in queryset:
            obj.token = secrets.token_urlsafe(48)
            obj.save(update_fields=['token'])
            count += 1
        self.message_user(request, f'🔐 已重新生成 {count} 个Agent Token')
    regenerate_tokens.short_description = '🔐 重新生成Token'

    def deactivate_stale(self, request, queryset):
        cutoff = tz_now() - timedelta(minutes=30)
        stale = queryset.filter(last_seen_at__lt=cutoff, is_active=True)
        count = stale.update(is_active=False)
        self.message_user(request, f'⏸ 已停用 {count} 个不活跃的Agent')
    deactivate_stale.short_description = '⏸ 停用不活跃Agent'


@admin.register(EscalationPolicy, site=monitoring_admin_site)
class EscalationPolicyAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'steps_detail', 'match_rules_preview']
    list_filter = ['is_active']
    list_editable = ['is_active']
    search_fields = ['name']

    def steps_detail(self, obj):
        steps = obj.escalation_steps or []
        if not steps:
            return '-'
        parts = []
        for i, step in enumerate(steps[:3]):
            delay = step.get('delay_minutes', 0)
            action = step.get('action', '')
            parts.append(f'Step{i+1}:{delay}m→{action}')
        text = ' | '.join(parts)
        if len(steps) > 3:
            text += f' (+{len(steps)-3})'
        return format_html('<span style="font-size:11px">{}</span>', text)
    steps_detail.short_description = '升级步骤'

    def match_rules_preview(self, obj):
        rules = obj.match_rules or {}
        return format_html('<code style="font-size:11px">{}</code>', str(rules)[:50])
    match_rules_preview.short_description = '匹配规则'


@admin.register(ServiceTopology, site=monitoring_admin_site)
class ServiceTopologyAdmin(admin.ModelAdmin):
    list_display = ['name', 'type_badge', 'server_link', 'health_indicator',
                    'dep_count_badge', 'impact_button']
    list_filter = ['service_type']
    filter_horizontal = ['depends_on']
    search_fields = ['name', 'server__hostname']

    def type_badge(self, obj):
        colors = {
            'application':'#1890ff','database':'#722ed1','cache':'#fa8c16',
            'queue':'#13c2c2','lb':'#52c41a','storage':'#eb2f96','external':'#999'
        }
        return format_html('<span style="background:{};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px">{}</span>',
                           colors.get(obj.service_type,'#1890ff'), obj.get_service_type_display())
    type_badge.short_description = '类型'

    def server_link(self, obj):
        if obj.server:
            return format_html('<a href="/admin/cmdb/server/{}/change/">{}</a>',
                              obj.server_id, obj.server.hostname)
        return '-'
    server_link.short_description = '服务器'

    def health_indicator(self, obj):
        from monitoring.topology.tracker import TopologyTracker
        h = TopologyTracker._node_health(obj)
        config = {
            'healthy':('✅ 健康','#52c41a'),
            'warning':('⚠️ 警告','#faad14'),
            'critical':('🔴 严重','#ff4d4f'),
            'unknown':('❓ 未知','#999')
        }
        icon, color = config.get(h, ('❓', '#999'))
        return format_html('<span style="color:{};font-weight:bold">{}</span>', color, icon)
    health_indicator.short_description = '健康状态'

    def dep_count_badge(self, obj):
        count = obj.depends_on.count()
        color = '#ff4d4f' if count >= 5 else '#faad14' if count >= 2 else '#52c41a'
        return format_html('<span style="background:{};color:#fff;padding:2px 6px;border-radius:8px">{}</span>', color, count)
    dep_count_badge.short_description = '依赖数'

    def impact_button(self, obj):
        url = f'/monitoring/admin/monitoring/servicetopology/{obj.id}/'
        return format_html('<a href="{}?impact=1" class="button" style="padding:2px 8px;background:#1890ff;color:white;border-radius:3px;text-decoration:none;font-size:11px">影响分析</a>', url)
    impact_button.short_description = '操作'
    impact_button.allow_tags = True


@admin.register(SavedDashboard, site=monitoring_admin_site)
class SavedDashboardAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner_link', 'visibility', 'share_token_code', 'widgets_count', 'updated_at']
    list_filter = ['is_public']
    search_fields = ['name']

    def owner_link(self, obj):
        if obj.owner:
            return format_html('<a href="/admin/auth/user/{}/change/">{}</a>',
                              obj.owner_id, obj.owner.username)
        return '-'
    owner_link.short_description = '所有者'

    def visibility(self, obj):
        if obj.is_public:
            return format_html('<span style="color:#52c41a">🌐 公开分享</span>')
        return format_html('<span style="color:#999">🔒 仅自己可见</span>')
    visibility.short_description = '可见性'

    def share_token_code(self, obj):
        if obj.share_token:
            return format_html('<code style="font-size:11px">{}</code>', obj.share_token)
        return format_html('<span style="color:#999">未生成</span>')
    share_token_code.short_description = '分享令牌'

    def widgets_count(self, obj):
        config = obj.config or {}
        widgets = config.get('widgets', [])
        return len(widgets)
    widgets_count.short_description = '组件数'


@admin.register(HealthScore, site=monitoring_admin_site)
class HealthScoreAdmin(ExportMixin, admin.ModelAdmin):
    list_display = ['server_link', 'overall_score_gauge', 'grade_badge',
                    'cpu_bar', 'mem_bar', 'disk_bar', 'scored_at']
    list_filter = ['grade']
    date_hierarchy = 'scored_at'
    actions = ['export_as_csv', 'export_as_excel', 'trigger_rescan']

    def has_add_permission(self, request):
        return False

    def server_link(self, obj):
        if obj.server:
            return format_html('<a href="/admin/cmdb/server/{}/change/">{}</a>',
                              obj.server_id, obj.server.hostname)
        return '-'
    server_link.short_description = '服务器'

    def overall_score_gauge(self, obj):
        score = obj.overall_score or 0
        if score >= 90:
            color = '#52c41a'
        elif score >= 70:
            color = '#1890ff'
        elif score >= 50:
            color = '#faad14'
        else:
            color = '#ff4d4f'
        return format_html('''
            <div style="width:60px;text-align:center">
            <div style="font-size:14px;font-weight:bold;color:{}">{:.0f}</div>
            <div style="height:4px;background:#f0f0f0;border-radius:2px;margin-top:2px">
            <div style="width:{}%;height:100%;background:{};border-radius:2px"></div>
            </div></div>
        ''', color, score, score, color)
    overall_score_gauge.short_description = '总分'
    overall_score_gauge.admin_order_field = 'overall_score'

    def grade_badge(self, obj):
        colors = {'A':'#52c41a','B':'#1890ff','C':'#faad14','D':'#ff4d4f','F':'#cf1322'}
        desc = {'A':'优秀','B':'良好','C':'一般','D':'较差','F':'危险'}
        return format_html(
            '<span style="background:{};color:#fff;padding:3px 10px;border-radius:12px;font-weight:bold;font-size:12px">{}级 ({})</span>',
            colors.get(obj.grade, '#999'), obj.grade, desc.get(obj.grade, '')
        )
    grade_badge.short_description = '等级'

    def cpu_bar(self, obj):
        return self._score_bar(obj.cpu_score)
    cpu_bar.short_description = 'CPU'
    cpu_bar.admin_order_field = 'cpu_score'

    def mem_bar(self, obj):
        return self._score_bar(obj.mem_score)
    mem_bar.short_description = '内存'
    mem_bar.admin_order_field = 'mem_score'

    def disk_bar(self, obj):
        return self._score_bar(obj.disk_score)
    disk_bar.short_description = '磁盘'
    disk_bar.admin_order_field = 'disk_score'

    def _score_bar(self, score):
        s = score or 0
        color = '#52c41a' if s >= 80 else '#faad14' if s >= 50 else '#ff4d4f'
        return format_html('<div style="width:50px"><div style="font-size:11px;text-align:right">{:.0f}</div>'
                          '<div style="height:6px;background:#f0f0f0;border-radius:3px">'
                          '<div style="width:{}%;height:100%;background:{};border-radius:3px"></div></div></div>',
                          s, s, color)

    def trigger_rescan(self, request, queryset):
        from monitoring.health.scorer import HealthScorer
        servers = list({obj.server for obj in queryset if obj.server})
        results = HealthScorer.scan_all_servers(servers=servers)
        self.message_user(request, f'🔄 已触发 {len(servers)} 台服务器的健康扫描，生成 {len(results)} 条新评分')
    trigger_rescan.short_description = '🔄 触发重新扫描'


# ============================================================
# 在默认 AdminSite 也注册这些模型（保持向后兼容）
# ============================================================

for model_admin_class in [
    (AlertRule, AlertRuleAdmin),
    (AlertEvent, AlertEventAdmin),
    (AlertSilenceRule, AlertSilenceRuleAdmin),
    (NotificationLog, NotificationLogAdmin),
    (DetectorConfig, DetectorConfigAdmin),
    (AnomalyHistory, AnomalyHistoryAdmin),
    (AlertGroup, AlertGroupAdmin),
    (AlertCorrelationRule, AlertCorrelationRuleAdmin),
    (RemediationAction, RemediationActionAdmin),
    (RemediationHistory, RemediationHistoryAdmin),
    (RunbookEntry, RunbookEntryAdmin),
    (AgentToken, AgentTokenAdmin),
    (EscalationPolicy, EscalationPolicyAdmin),
    (ServiceTopology, ServiceTopologyAdmin),
    (SavedDashboard, SavedDashboardAdmin),
    (HealthScore, HealthScoreAdmin),
]:
    admin.site.register(model_admin_class[0], model_admin_class[1])
