from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from log_analysis.models import LogEntry
from ai_ops.utils import ask_ai
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def ai_log_summary(self, log_entry_ids=None, hours=24, batch_size=100):
    """
    AI日志摘要任务 - 调用LLM API生成异常日志摘要
    
    :param log_entry_ids: 可选，指定要处理的日志条目ID列表
    :param hours: 时间范围（小时），默认24小时
    :param batch_size: 每批处理的日志数量，默认100条
    """
    try:
        if log_entry_ids:
            logs = LogEntry.objects.filter(id__in=log_entry_ids)
        else:
            start_time = timezone.now() - timedelta(hours=hours)
            logs = LogEntry.objects.filter(
                timestamp__gte=start_time,
                level__in=['error', 'critical', 'warning']
            ).order_by('-timestamp')
        
        if not logs.exists():
            logger.info("[ai_log_summary] 没有需要处理的异常日志")
            return {"result": "no logs to process", "count": 0}

        all_logs = list(logs)
        total_count = len(all_logs)
        summaries = []
        
        for i in range(0, total_count, batch_size):
            batch = all_logs[i:i + batch_size]
            
            logs_list = []
            for log in batch:
                logs_list.append({
                    'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    'level': log.level.upper(),
                    'server': log.server.hostname if log.server else 'Unknown',
                    'source': log.source.name,
                    'message': log.message[:500]
                })

            prompt = f"""
请对以下异常日志进行分析并生成摘要：

日志列表（共{len(logs_list)}条）：
{chr(10).join([f"{i+1}. [{log['timestamp']}] [{log['level']}] {log['server']} ({log['source']}): {log['message']}" for i, log in enumerate(logs_list)])}

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
                if self.request.retries < self.max_retries:
                    raise self.retry(exc=Exception(response['error']), countdown=60)
                return {"result": "failed", "error": response['error']}

            summary = response.get('content', '')
            summaries.append(summary)
            logger.info(f"[ai_log_summary] 完成批次 {i//batch_size + 1}/{(total_count-1)//batch_size + 1}")

        final_summary = "\n\n".join(summaries)
        if len(summaries) > 1:
            final_summary = f"=== 综合摘要 ({total_count}条日志) ===\n\n" + final_summary

        logger.info(f"[ai_log_summary] 成功生成日志摘要，共处理 {total_count} 条日志")
        
        return {
            "result": "success",
            "count": total_count,
            "summary": final_summary
        }

    except Exception as e:
        logger.error(f"[ai_log_summary] 执行失败: {e}")
        return {"result": "failed", "error": str(e)}


@shared_task
def batch_process_log_summaries(hours_list=None):
    """
    批量处理不同时间范围的日志摘要
    
    :param hours_list: 时间范围列表，如 [1, 6, 24]，分别表示1小时、6小时、24小时
    """
    if not hours_list:
        hours_list = [1, 6, 24]
    
    results = []
    for hours in hours_list:
        result = ai_log_summary.delay(hours=hours)
        results.append({
            'hours': hours,
            'task_id': result.task_id,
            'status': 'pending'
        })
    
    return {"result": "tasks submitted", "tasks": results}