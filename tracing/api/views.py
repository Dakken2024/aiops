import json
import base64
import logging
from datetime import datetime, timezone

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET

from tracing.models import Trace, Span

logger = logging.getLogger(__name__)


def _extract_attr_value(attr):
    value = attr.get('value', {})
    if 'stringValue' in value:
        return value['stringValue']
    elif 'intValue' in value:
        return int(value['intValue'])
    elif 'doubleValue' in value:
        return float(value['doubleValue'])
    elif 'boolValue' in value:
        return value['boolValue']
    return str(value)


def _parse_otlp_timestamp(nano_str):
    try:
        nanos = int(nano_str)
        seconds = nanos // 1_000_000_000
        dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
        return dt.replace(tzinfo=None)
    except (ValueError, TypeError, OSError):
        return datetime.now()


def _parse_span(span_data, resource_attrs):
    try:
        trace_id = base64.b64decode(span_data.get('traceId', '')).hex() if span_data.get('traceId') else ''
        span_id = base64.b64decode(span_data.get('spanId', '')).hex() if span_data.get('spanId') else ''
        parent_span_id = ''
        if span_data.get('parentSpanId'):
            parent_span_id = base64.b64decode(span_data['parentSpanId']).hex()

        start_time = _parse_otlp_timestamp(span_data.get('startTimeUnixNano', '0'))
        end_time = _parse_otlp_timestamp(span_data.get('endTimeUnixNano', '0'))
        duration_ms = int((end_time - start_time).total_seconds() * 1000) if end_time > start_time else 0

        status_code = 'ok'
        status_data = span_data.get('status', {})
        if status_data.get('code') == 2:
            status_code = 'error'

        attributes = {}
        if span_data.get('attributes'):
            attributes = {
                attr['key']: _extract_attr_value(attr)
                for attr in span_data['attributes']
            }

        service_name = resource_attrs.get('service.name', '')
        name = span_data.get('name', '')

        return {
            'trace_id': trace_id[:32],
            'span_id': span_id[:16],
            'parent_span_id': parent_span_id[:16] if parent_span_id else None,
            'service_name': service_name,
            'name': name,
            'start_time': start_time,
            'duration_ms': duration_ms,
            'status_code': status_code,
            'attributes': {**resource_attrs, **attributes},
        }
    except Exception as e:
        logger.debug(f"[OTLP] 解析Span失败: {e}")
        return None


def parse_otlp_http(body):
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return []

    spans = []
    resource_spans = data.get('resourceSpans', [])

    for rs in resource_spans:
        resource_attrs = {}
        if rs.get('resource', {}).get('attributes'):
            resource_attrs = {
                attr['key']: _extract_attr_value(attr)
                for attr in rs['resource']['attributes']
            }

        for scope_spans in rs.get('scopeSpans', []):
            for span_data in scope_spans.get('spans', []):
                span = _parse_span(span_data, resource_attrs)
                if span:
                    spans.append(span)

    return spans


@csrf_exempt
@require_POST
def otlp_receiver(request):
    try:
        spans = parse_otlp_http(request.body)
        if not spans:
            return JsonResponse({'code': 0, 'data': {'spans_received': 0, 'spans_created': 0}})

        trace_cache = {}
        created = 0

        for span_data in spans:
            trace_id = span_data['trace_id']
            
            if trace_id not in trace_cache:
                trace, _ = Trace.objects.get_or_create(
                    trace_id=trace_id,
                    defaults={
                        'name': span_data['service_name'],
                        'start_time': span_data['start_time'],
                    }
                )
                trace_cache[trace_id] = trace
            else:
                trace = trace_cache[trace_id]

            if span_data['start_time'] < trace.start_time:
                trace.start_time = span_data['start_time']
            
            end_time_candidate = span_data['start_time'] + datetime.timedelta(milliseconds=span_data['duration_ms'])
            if not trace.end_time or end_time_candidate > trace.end_time:
                trace.end_time = end_time_candidate
            
            Span.objects.create(
                trace=trace,
                span_id=span_data['span_id'],
                parent_span_id=span_data.get('parent_span_id'),
                name=span_data['name'],
                start_time=span_data['start_time'],
                duration_ms=span_data['duration_ms'],
                status_code=span_data['status_code'],
                attributes=span_data.get('attributes', {}),
            )
            created += 1

        for trace in trace_cache.values():
            if trace.end_time:
                trace.duration_ms = int((trace.end_time - trace.start_time).total_seconds() * 1000)
            trace.save()

        return JsonResponse({'code': 0, 'data': {'spans_received': len(spans), 'spans_created': created}})
    except Exception as e:
        logger.error(f"[OTLP] 接收失败: {e}")
        return JsonResponse({'code': 1, 'msg': str(e)}, status=500)


@require_GET
def trace_detail(request, trace_id):
    try:
        trace = Trace.objects.get(trace_id=trace_id)
        spans = list(Span.objects.filter(trace=trace).order_by('start_time').values(
            'span_id', 'parent_span_id', 'name', 'start_time', 'duration_ms',
            'status_code', 'attributes'
        ))
        
        data = {
            'trace_id': trace.trace_id,
            'name': trace.name,
            'start_time': trace.start_time.isoformat(),
            'end_time': trace.end_time.isoformat() if trace.end_time else None,
            'duration_ms': trace.duration_ms,
            'tags': trace.tags,
            'spans': spans,
        }
        return JsonResponse({'code': 0, 'data': data})
    except Trace.DoesNotExist:
        return JsonResponse({'code': 1, 'msg': 'Trace不存在'}, status=404)


@require_GET
def trace_list(request):
    from django.db.models import Count
    traces = Trace.objects.annotate(span_count=Count('spans')).order_by('-start_time')[:50]
    data = [{
        'trace_id': t.trace_id,
        'name': t.name,
        'start_time': t.start_time.isoformat(),
        'duration_ms': t.duration_ms,
        'span_count': t.span_count,
    } for t in traces]
    return JsonResponse({'code': 0, 'data': {'items': data}})


@require_GET
def service_list(request):
    services = Trace.objects.values('name').distinct()
    data = [{'name': s['name']} for s in services]
    return JsonResponse({'code': 0, 'data': {'items': data}})
