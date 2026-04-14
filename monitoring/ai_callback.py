import json
import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def anomaly_ai_callback_task(self, event_id, server_id=None, metric_name='cpu_usage'):
    from monitoring.models import AlertEvent, AnomalyHistory
    from cmdb.models import Server, ServerMetric
    from datetime import timedelta
    try:
        event = AlertEvent.objects.select_related('rule', 'server').get(id=event_id)
    except AlertEvent.DoesNotExist:
        logger.warning(f"[AICallback] 事件{event_id}不存在")
        return {'error': 'event_not_found'}
    if not server_id and event.server:
        server_id = event.server.id
    if not server_id:
        logger.warning(f"[AICallback] 事件{event_id}无关联服务器，跳过AI诊断")
        return {'error': 'no_server'}
    try:
        server = Server.objects.get(id=server_id)
    except Server.DoesNotExist:
        return {'error': 'server_not_found'}
    since = timezone.now() - timedelta(minutes=20)
    try:
        metrics = ServerMetric.objects.filter(
            server=server,
            collected_at__gte=since,
        ).order_by('-collected_at')[:20]
        if not metrics.exists():
            logger.info(f"[AICallback] 服务器{server.hostname}无最近指标数据，跳过")
            return {'error': 'no_metrics'}
        context = _build_diagnostic_context(server, metrics, event, metric_name)
        analysis = _call_ai_diagnose(context)
        if not analysis:
            logger.warning(f"[AICallback] AI诊断返回空结果")
            return {'error': 'ai_empty_response'}
        now = timezone.now()
        detail = event.detail or {}
        detail['ai_diagnosis'] = {
            'analysis': analysis.get('analysis', ''),
            'suggestions': analysis.get('suggestions', []),
            'confidence': analysis.get('confidence', 0),
            'analyzed_at': now.isoformat(),
            'model_used': analysis.get('model', 'default'),
        }
        event.detail = detail
        event.save(update_fields=['detail'])
        anomaly_history = AnomalyHistory.objects.filter(alert_event=event).first()
        if anomaly_history:
            anomaly_history.ai_diagnosis = analysis.get('analysis', '')
            anomaly_history.ai_confidence = analysis.get('confidence')
            anomaly_history.ai_analyzed_at = now
            anomaly_history.save(update_fields=['ai_diagnosis', 'ai_confidence', 'ai_analyzed_at'])
        logger.info(f"[AICallback] 事件{event_id} AI诊断完成, 置信度={analysis.get('confidence', 0)}")
        return {
            'status': 'success',
            'event_id': event_id,
            'confidence': analysis.get('confidence', 0),
            'has_suggestions': bool(analysis.get('suggestions')),
        }
    except Exception as e:
        logger.error(f"[AICallback] 事件{event_id} AI诊断失败: {e}", exc_info=True)
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60 * (self.request.retries + 1))
        return {'error': str(e)}


def _build_diagnostic_context(server, metrics, event, metric_name):
    latest = metrics.first()
    data_points = []
    for m in reversed(list(metrics)):
        data_points.append({
            'time': m.collected_at.strftime('%H:%M:%S'),
            'cpu': getattr(m, 'cpu_usage', 0),
            'mem': getattr(m, 'mem_usage', 0),
            'disk': getattr(m, 'disk_usage', 0),
            'load': getattr(m, 'load_1min', 0),
        })
    anomaly_info = event.detail or {}
    context = {
        'hostname': server.hostname,
        'ip': server.ip_address,
        'os': getattr(server, 'os_info', None) or 'Unknown',
        'triggered_rule': event.rule.name if event.rule else 'Unknown',
        'triggered_metric': metric_name,
        'current_value': event.current_value,
        'threshold': event.threshold_value,
        'anomaly_score': anomaly_info.get('anomaly_score', 0),
        'method_used': anomaly_info.get('method_used', 'unknown'),
        'recent_metrics': data_points[-15:],
        'summary': {
            'avg_cpu': sum(d['cpu'] for d in data_points) / len(data_points) if data_points else 0,
            'avg_mem': sum(d['mem'] for d in data_points) / len(data_points) if data_points else 0,
            'peak_cpu': max((d['cpu'] for d in data_points), default=0),
            'peak_mem': max((d['mem'] for d in data_points), default=0),
            'trend': 'rising' if len(data_points) >= 2 and data_points[-1]['cpu'] > data_points[0]['cpu'] else 'stable',
        }
    }
    return context


def _call_ai_diagnose(context):
    import os
    api_key = os.environ.get('OPENAI_API_KEY', '') or os.environ.get('QWEN_API_KEY', '')
    base_url = os.environ.get('OPENAI_BASE_URL', '') or os.environ.get('QWEN_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
    model = os.environ.get('AI_DIAGNOSE_MODEL', 'qwen-plus')
    
    if not api_key:
        logger.warning("[AICallback] 未配置 API Key (OPENAI_API_KEY / QWEN_API_KEY)")
        return None
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
    except ImportError:
        logger.warning("[AICallback] openai 库未安装, 请执行: pip install openai")
        return None

    system_prompt = """你是阿里云通义千问 Qwen3 驱动的 AIOps（智能运维）诊断专家。你的职责是：
1. 基于监控数据精准定位异常根因
2. 给出可执行的修复建议
3. 评估问题紧急程度和置信度

分析原则：
- 优先判断是否为正常业务波动（如定时任务、流量波峰）
- 关注指标间的因果关系（CPU↑ → 内存↑ → 磁盘IO↑）
- 结合历史趋势判断是突发还是渐进恶化
- 区分资源不足、配置缺陷、外部攻击等根因类型"""

    user_prompt = f"""请对以下告警事件进行智能根因分析：

## 🖥️ 目标服务器
| 字段 | 值 |
|------|-----|
| 主机名 | {context['hostname']} |
| IP地址 | {context['ip']} |
| 操作系统 | {context['os']} |

## 🚨 告警详情
| 字段 | 值 |
|------|-----|
| 触发规则 | {context['triggered_rule']} |
| 监控指标 | {context['triggered_metric']} |
| 当前值 | {context['current_value']} |
| 阈值/基线 | {context.get('threshold', 'N/A')} |
| 异常分数 | {context['anomaly_score']} |
| 检测算法 | {context['method_used']} |

## 📈 近期指标采样 (最近15个点)
```
时间        CPU(%)   MEM(%)   Load
{''.join([f"{d['time']:>8s}  {d['cpu']:>6.1f}  {d['mem']:>6.1f}  {d['load']:>6.2f}" + chr(10) for d in context['recent_metrics']])}
```

## 📊 统计摘要
- CPU均值: {context['summary']['avg_cpu']:.1f}% | 峰值: {context['summary']['peak_cpu']:.1f}%
- 内存均值: {context['summary']['avg_mem']:.1f}% | 峰值: {context['summary']['peak_mem']}%
- 趋势: {'📈 持续上升' if context['summary']['trend'] == 'rising' else '➡️ 相对稳定'}

请以严格 JSON 格式返回（不要包含 markdown 代码块标记）：
{{
    "analysis": "根因分析（150字以内，说明最可能的原因及推理依据）",
    "suggestions": ["具体可操作的修复建议1", "建议2", "建议3"],
    "confidence": 0.85,
    "root_cause_category": "resource_exhaustion|config_error|security_incident|noise|network_issue|other",
    "urgency": "immediate|high|medium|low"
}}"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2,
            max_tokens=1024,
            response_format={"type": "json_object"},
            top_p=0.9,
        )
        
        content = response.choices[0].message.content
        
        if content.startswith("```"):
            import re
            content = re.sub(r'^```(?:json)?\s*', '', content)
            content = re.sub(r'```\s*$', '', content)
        
        result = json.loads(content.strip())
        
        category_map = {
            '资源不足': 'resource_exhaustion',
            '配置错误': 'config_error',
            '外部攻击/安全事件': 'security_incident',
            '安全事件': 'security_incident',
            '正常波动/噪声': 'noise',
            '正常波动': 'noise',
            '网络问题': 'network_issue',
        }
        if result.get('root_cause_category') in category_map:
            result['root_cause_category'] = category_map[result['root_cause_category']]
        
        logger.info(f"[AICallback] Qwen3 诊断完成, 置信度={result.get('confidence', 0)}, "
                     f"根因={result.get('root_cause_category', '-')}, "
                     f"model={model}")
        
        return result
        
    except json.JSONDecodeError as e:
        logger.error(f"[AICallback] JSON解析失败: {e}, raw={content[:200]}")
        return None
    except Exception as e:
        logger.error(f"[AICallback] AI调用异常: {e}")
        if hasattr(e, 'status_code'):
            logger.error(f"[AICallback] HTTP状态码: {getattr(e, 'status_code', '?')}")
        return None