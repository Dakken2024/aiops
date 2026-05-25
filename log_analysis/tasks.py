from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import LogEntry, LogAlertRule, LogAlert, LogPattern
from ai_ops.utils import ask_ai
import logging
import re

logger = logging.getLogger(__name__)


@shared_task
def ai_log_summary(log_entry_ids=None, hours=24):
    """
    AI日志摘要任务 - 调用LLM API生成异常日志摘要
    
    :param log_entry_ids: 可选，指定要处理的日志条目ID列表
    :param hours: 时间范围（小时），默认24小时
    """
    try:
        if log_entry_ids:
            logs = LogEntry.objects.filter(id__in=log_entry_ids)
        else:
            start_time = timezone.now() - timedelta(hours=hours)
            logs = LogEntry.objects.filter(
                timestamp__gte=start_time,
                level__in=['error', 'critical', 'warning']
            )
        
        if not logs.exists():
            logger.info("[ai_log_summary] 没有需要处理的异常日志")
            return {"result": "no logs to process", "count": 0}

        logs_list = []
        for log in logs:
            logs_list.append({
                'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'level': log.level.upper(),
                'server': log.server.hostname if log.server else 'Unknown',
                'message': log.message[:500]
            })

        prompt = f"""
请对以下异常日志进行分析并生成摘要：

日志列表（共{len(logs_list)}条）：
{chr(10).join([f"{i+1}. [{log['timestamp']}] [{log['level']}] {log['server']}: {log['message']}" for i, log in enumerate(logs_list)])}

请输出：
1. 问题概述：简要描述检测到的主要问题
2. 问题分类：按错误类型/服务/组件进行分类统计
3. 根因分析：分析可能的根本原因
4. 建议措施：给出针对性的处理建议
5. 严重程度：评估整体风险等级（低/中/高/严重）

请用中文回复，格式清晰易读。
"""

        response = ask_ai(prompt, system_role="你是一位专业的DevOps工程师和系统分析师。请对日志进行深入分析并提供专业的技术建议。")
        
        if 'error' in response:
            logger.error(f"[ai_log_summary] AI调用失败: {response['error']}")
            return {"result": "failed", "error": response['error']}

        summary = response.get('content', '')
        logger.info(f"[ai_log_summary] 成功生成日志摘要")
        
        return {
            "result": "success",
            "count": len(logs_list),
            "summary": summary
        }

    except Exception as e:
        logger.error(f"[ai_log_summary] 执行失败: {e}")
        return {"result": "failed", "error": str(e)}


@shared_task
def check_log_alerts():
    """
    检查日志告警规则并触发告警
    """
    try:
        rules = LogAlertRule.objects.filter(is_enabled=True)
        
        for rule in rules:
            start_time = timezone.now() - timedelta(minutes=rule.time_window_minutes)
            
            query = LogEntry.objects.filter(timestamp__gte=start_time)
            
            if rule.level_filter:
                levels = [l.strip() for l in rule.level_filter.split(',')]
                query = query.filter(level__in=levels)
            
            if rule.trigger_type == 'keyword':
                if rule.keywords:
                    keyword_conditions = [LogEntry.message__icontains=kw for kw in rule.keywords]
                    from django.db.models import Q
                    query = query.filter(Q(*keyword_conditions))
            
            elif rule.trigger_type == 'pattern' and rule.pattern_id:
                pattern = rule.pattern_id
                query = query.filter(pattern=pattern)
            
            count = query.count()
            
            if count >= rule.threshold_count:
                active_alerts = LogAlert.objects.filter(
                    rule=rule,
                    status='firing'
                )
                
                if not active_alerts.exists():
                    LogAlert.objects.create(
                        rule=rule,
                        server=query.first().server if query.exists() else None,
                        message=f"告警规则 '{rule.name}' 触发，在{rule.time_window_minutes}分钟内检测到{count}条匹配日志",
                        detail={
                            'count': count,
                            'time_window_minutes': rule.time_window_minutes,
                            'threshold': rule.threshold_count
                        }
                    )
                    
                    rule.last_triggered_at = timezone.now()
                    rule.trigger_count += 1
                    rule.save()
                    
                    logger.info(f"[check_log_alerts] 触发告警: {rule.name}")
        
        return {"result": "success"}
    
    except Exception as e:
        logger.error(f"[check_log_alerts] 执行失败: {e}")
        return {"result": "failed", "error": str(e)}


@shared_task
def process_new_logs(log_entry_ids):
    """
    处理新收到的日志条目（模式匹配和告警检查）
    """
    try:
        for log_id in log_entry_ids:
            try:
                log_entry = LogEntry.objects.get(id=log_id)
                _match_pattern(log_entry)
                _check_single_log_alerts(log_entry)
            except LogEntry.DoesNotExist:
                continue
        
        return {"result": "success", "count": len(log_entry_ids)}
    
    except Exception as e:
        logger.error(f"[process_new_logs] 执行失败: {e}")
        return {"result": "failed", "error": str(e)}


def _match_pattern(log_entry):
    """匹配日志模式"""
    patterns = LogPattern.objects.all()
    for pattern in patterns:
        try:
            if re.search(pattern.pattern, log_entry.message):
                log_entry.pattern = pattern
                log_entry.save()
                
                pattern.occurrences += 1
                pattern.last_seen = timezone.now()
                pattern.save()
                break
        except re.error:
            continue


def _check_single_log_alerts(log_entry):
    """检查单条日志是否触发告警规则"""
    rules = LogAlertRule.objects.filter(is_enabled=True)
    
    for rule in rules:
        if rule.level_filter:
            levels = [l.strip() for l in rule.level_filter.split(',')]
            if log_entry.level not in levels:
                continue
        
        if rule.trigger_type == 'keyword':
            if rule.keywords:
                matched = any(kw.lower() in log_entry.message.lower() for kw in rule.keywords)
                if not matched:
                    continue
        
        elif rule.trigger_type == 'pattern' and rule.pattern_id:
            if log_entry.pattern != rule.pattern_id:
                continue
        
        start_time = timezone.now() - timedelta(minutes=rule.time_window_minutes)
        count = LogEntry.objects.filter(
            timestamp__gte=start_time,
            level=log_entry.level
        ).count()
        
        if count >= rule.threshold_count:
            active_alerts = LogAlert.objects.filter(rule=rule, status='firing')
            if not active_alerts.exists():
                LogAlert.objects.create(
                    rule=rule,
                    server=log_entry.server,
                    message=f"告警规则 '{rule.name}' 触发",
                    detail={'log_message': log_entry.message[:200]}
                )
                
                rule.last_triggered_at = timezone.now()
                rule.trigger_count += 1
                rule.save()