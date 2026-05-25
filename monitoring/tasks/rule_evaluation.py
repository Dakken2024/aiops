"""
规则评估 Celery 任务
支持并行分片执行告警规则评估
"""

import logging
from celery import shared_task
from django.utils import timezone
from django.db import models as dj_models

from monitoring.models import AlertRule, AlertEvent, AlertSilenceRule
from monitoring.engine.rule_evaluator import RuleEvaluator

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def evaluate_rule_chunk(self, rule_ids):
    """
    评估一批规则的 Celery 任务
    
    :param rule_ids: 规则 ID 列表
    :return: {'evaluated': int, 'fired': int, 'errors': list}
    """
    results = {'evaluated': 0, 'fired': 0, 'errors': []}
    
    rules = AlertRule.objects.filter(id__in=rule_ids, status='enabled')
    
    for rule in rules:
        try:
            evaluator = RuleEvaluator(rule)
            fired, _ = evaluator.evaluate()
            results['evaluated'] += 1
            if fired:
                results['fired'] += 1
        except Exception as e:
            logger.error(f"[RuleChunk] 规则{rule.id}评估异常: {e}")
            results['errors'].append({'rule_id': rule.id, 'error': str(e)})
    
    logger.info(f"[RuleChunk] 完成评估: {results['evaluated']}条规则, {results['fired']}条触发")
    return results


@shared_task
def evaluate_all_rules_parallel():
    """
    触发所有规则的并行评估
    由 Celery Beat 定时调用
    """
    from django.conf import settings
    chunk_size = getattr(settings, 'RULE_EVAL_CHUNK_SIZE', 50)
    
    results = RuleEvaluator.evaluate_all_parallel(chunk_size=chunk_size)
    logger.info(f"[ParallelEval] 总评估: {results['evaluated']}条, 触发: {results['fired']}条")
    return results
