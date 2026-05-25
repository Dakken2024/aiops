import logging
from celery import shared_task
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


@shared_task
def ai_log_summary(log_entry_ids=None, hours=24):
    """
    AI 日志摘要生成任务
    """
    from log_analysis.models import LogEntry
    
    if log_entry_ids:
        logs = LogEntry.objects.filter(id__in=log_entry_ids)
    else:
        start_time = timezone.now() - timedelta(hours=hours)
        logs = LogEntry.objects.filter(timestamp__gte=start_time)
    
    log_count = logs.count()
    error_count = logs.filter(level__in=['error', 'critical']).count()
    warning_count = logs.filter(level='warning').count()
    
    summary = {
        'total_logs': log_count,
        'error_count': error_count,
        'warning_count': warning_count,
        'info_count': log_count - error_count - warning_count,
        'time_range_hours': hours,
        'generated_at': timezone.now().isoformat(),
        'summary_text': f"在过去{hours}小时内，共收集到{log_count}条日志，其中错误{error_count}条，警告{warning_count}条。",
    }
    
    logger.info(f"[LogSummary] 生成摘要完成: {log_count}条日志")
    return summary


@shared_task
def check_log_alerts():
    """
    检查日志告警规则任务
    """
    from log_analysis.models import LogAlertRule, LogAlert, LogEntry
    from datetime import timedelta
    
    rules = LogAlertRule.objects.filter(is_enabled=True)
    checked_count = 0
    alert_count = 0
    
    for rule in rules:
        try:
            time_window = timedelta(minutes=rule.time_window_minutes)
            recent_logs = LogEntry.objects.filter(
                source=rule.source,
                timestamp__gte=timezone.now() - time_window,
            )
            
            match_count = 0
            for log in recent_logs:
                if rule.trigger_type == 'keyword' and rule.keywords:
                    keywords = [kw.strip().lower() for kw in rule.keywords.split(',')]
                    if any(kw in log.message.lower() for kw in keywords):
                        match_count += 1
                
                if rule.level_filter:
                    levels = [l.strip().lower() for l in rule.level_filter.split(',')]
                    if log.level.lower() in levels:
                        match_count += 1
            
            if match_count >= rule.threshold:
                LogAlert.objects.get_or_create(
                    rule=rule,
                    source=rule.source,
                    status='firing',
                    defaults={
                        'message': f"规则 {rule.name} 触发，匹配 {match_count} 次",
                        'details': {'match_count': match_count, 'threshold': rule.threshold},
                    }
                )
                alert_count += 1
            
            checked_count += 1
        except Exception as e:
            logger.error(f"[LogAlerts] 检查规则 {rule.name} 失败: {e}")
    
    logger.info(f"[LogAlerts] 检查完成: 检查{checked_count}条规则，触发{alert_count}条告警")
    return {'checked_rules': checked_count, 'alerts_created': alert_count}