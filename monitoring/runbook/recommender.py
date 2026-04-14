import logging
import math
from django.db.models import Q

from monitoring.models import RunbookEntry, AlertEvent

logger = logging.getLogger(__name__)


class RunbookRecommender:

    @staticmethod
    def recommend_for_alert(alert_event: AlertEvent, limit=5):
        rule_name = alert_event.rule.name if alert_event.rule else ''
        metric = alert_event.metric_name or ''
        severity = alert_event.severity or ''
        server_hostname = alert_event.server.hostname if alert_event.server else ''

        query = Q(is_published=True)

        query |= Q(problem_pattern__rule_name__icontains=rule_name)
        query |= Q(problem_pattern__metric_name__icontains=metric)
        query |= Q(title__icontains=metric)
        query |= Q(tags__icontains=metric)
        query |= Q(title__icontains=rule_name)

        entries = list(RunbookEntry.objects.filter(query))

        scored = []
        for entry in entries:
            score = RunbookRecommender._calc_score(entry, rule_name, metric, severity)
            if score > 0.05:
                scored.append((entry, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [
            {
                'id': entry.id,
                'title': entry.title,
                'category': entry.category,
                'solution': entry.solution[:500],
                'tags': entry.tag_list,
                'score': round(score, 3),
                'effectiveness': round(entry.effectiveness_score, 2),
                'usage_count': entry.usage_count,
            }
            for entry, score in scored[:limit]
        ]

    @staticmethod
    def search(query_text='', category=None, limit=20):
        qs = RunbookEntry.objects.filter(is_published=True)
        if query_text:
            qs = qs.filter(
                Q(title__icontains=query_text) |
                Q(solution__icontains=query_text) |
                Q(tags__icontains=query_text) |
                Q(problem_pattern__contains=query_text)
            )
        if category and category != 'all':
            qs = qs.filter(category=category)
        return list(qs[:limit])

    @staticmethod
    def record_feedback(entry_id, is_effective=True):
        try:
            entry = RunbookEntry.objects.get(id=entry_id)
            entry.usage_count += 1
            if is_effective:
                delta = 0.1 / (1 + math.log(entry.usage_count + 1))
                entry.effectiveness_score = min(1.0, entry.effectiveness_score + delta)
            else:
                entry.effectiveness_score = max(0.0, entry.effectiveness_score - 0.05)
            entry.save(update_fields=['usage_count', 'effectiveness_score'])
            logger.info(f"[Runbook] 反馈记录: id={entry_id} effective={is_effective}")
            return True
        except RunbookEntry.DoesNotExist:
            return False

    @staticmethod
    def _calc_score(entry, rule_name, metric, severity):
        score = 0.0
        patterns = entry.problem_pattern or {}

        if patterns.get('rule_name') == rule_name:
            score += 0.5
        elif rule_name and rule_name in (patterns.get('rule_name') or ''):
            score += 0.25

        if patterns.get('metric_name') == metric:
            score += 0.4
        elif metric and metric in (patterns.get('metric_name') or ''):
            score += 0.15

        if metric and metric in (entry.tags or ''):
            score += 0.2

        if severity and severity in (patterns.get('severities') or []):
            score += 0.1

        base = entry.effectiveness_score or 0.0
        usage_factor = math.log(entry.usage_count + 1) * 0.02

        return score * 0.7 + base * 0.2 + usage_factor
