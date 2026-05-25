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
        correlation_context = None
        try:
            from monitoring.correlation.correlator import Correlator
            correlation_context = Correlator.correlate_all(event)
        except Exception as e:
            logger.warning(f"[AIv2] 多源关联失败: {e}")

        related_logs_text = ""
        related_traces_text = ""
        similar_cases_text = ""

        if correlation_context:
            logs = correlation_context.get('related_logs', [])
            if logs:
                related_logs_text = "\n## 关联日志异常 (告警前后5分钟)\n"
                for log in logs[:10]:
                    related_logs_text += f"- [{log.get('level','')}] {log.get('message','')[:150]}\n"

            traces = correlation_context.get('related_traces', {})
            if isinstance(traces, dict):
                errors = traces.get('errors', [])
                slow = traces.get('slow', [])
                if errors or slow:
                    related_traces_text = "\n## 关联链路异常 (告警前后5分钟)\n"
                    for s in errors[:5]:
                        related_traces_text += f"- [ERROR] {s.get('service_name','')} {s.get('operation','')} ({s.get('duration_ms',0)}ms) {s.get('error_message','')[:100]}\n"
                    for s in slow[:5]:
                        related_traces_text += f"- [SLOW] {s.get('service_name','')} {s.get('operation','')} ({s.get('duration_ms',0)}ms)\n"

            cases = correlation_context.get('similar_cases', [])
            if cases:
                similar_cases_text = "\n## 历史相似案例\n"
                for c in cases[:3]:
                    similar_cases_text += f"- 案例#{c.get('id','')}: {c.get('root_cause','')[:100]} → 修复: {c.get('remediation','')[:100]} (有效性={c.get('effectiveness_score',0):.1f})\n"

        context = _build_diagnostic_context(server, metrics, event, metric_name)
        analysis = _call_ai_diagnose(context, related_logs_text, related_traces_text, similar_cases_text)
        if not analysis:
            logger.warning(f"[AICallback] AI诊断返回空结果")
            return {'error': 'ai_empty_response'}
        now = timezone.now()
        detail = event.detail or {}
        detail['ai_diagnosis'] = {
            'root_cause': analysis.get('root_cause', ''),
            'root_cause_category': analysis.get('root_cause_category', ''),
            'confidence': analysis.get('confidence', 0),
            'impact_scope': analysis.get('impact_scope', ''),
            'remediation_suggestion': analysis.get('remediation_suggestion', ''),
            'remediation_command': analysis.get('remediation_command', ''),
            'is_dangerous': analysis.get('is_dangerous', False),
            'urgency': analysis.get('urgency', ''),
            'reasoning': analysis.get('reasoning', ''),
            'analyzed_at': now.isoformat(),
            'model_used': analysis.get('model', 'default'),
        }
        event.detail = detail
        event.save(update_fields=['detail'])

        confidence = 0.0
        try:
            if isinstance(analysis, dict):
                confidence = float(analysis.get('confidence', 0.0))
        except (ValueError, TypeError):
            confidence = 0.0

        anomaly_history = AnomalyHistory.objects.filter(alert_event=event).first()
        if anomaly_history:
            diagnosis_text = analysis.get('root_cause', '') or analysis.get('analysis', '')
            anomaly_history.ai_diagnosis = diagnosis_text
            anomaly_history.confidence = confidence
            anomaly_history.ai_confidence = confidence
            anomaly_history.ai_analyzed_at = now
            anomaly_history.save(update_fields=['ai_diagnosis', 'confidence', 'ai_confidence', 'ai_analyzed_at'])
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


def _call_ai_diagnose(context, related_logs_text="", related_traces_text="", similar_cases_text=""):
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
{related_logs_text}
{related_traces_text}
{similar_cases_text}

请输出JSON格式:
{{
  "root_cause": "根因分析",
  "root_cause_category": "分类(network/disk/memory/cpu/service/config/unknown)",
  "confidence": 0.0,
  "impact_scope": "影响范围评估",
  "remediation_suggestion": "修复建议",
  "remediation_command": "可执行的修复命令(如有)",
  "is_dangerous": false,
  "urgency": "high/medium/low",
  "reasoning": "分析推理过程"
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