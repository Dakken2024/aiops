import json
import logging
import base64
from datetime import datetime, timezone
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def parse_otlp_http(body: bytes) -> List[Dict[str, Any]]:
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


def _parse_span(span_data: Dict, resource_attrs: Dict) -> Dict[str, Any]:
    try:
        trace_id = base64.b64decode(span_data.get('traceId', '')).hex() if span_data.get('traceId') else ''
        span_id = base64.b64decode(span_data.get('spanId', '')).hex() if span_data.get('spanId') else ''
        parent_span_id = ''
        if span_data.get('parentSpanId'):
            parent_span_id = base64.b64decode(span_data['parentSpanId']).hex()

        start_time = _parse_otlp_timestamp(span_data.get('startTimeUnixNano', '0'))
        end_time = _parse_otlp_timestamp(span_data.get('endTimeUnixNano', '0'))
        duration_ms = int((end_time - start_time).total_seconds() * 1000) if end_time > start_time else 0

        status = 'UNSET'
        status_data = span_data.get('status', {})
        if status_data.get('code') == 2:
            status = 'ERROR'
        elif status_data.get('code') == 1:
            status = 'OK'

        error_message = status_data.get('message', '')

        attributes = {}
        if span_data.get('attributes'):
            attributes = {
                attr['key']: _extract_attr_value(attr)
                for attr in span_data['attributes']
            }

        service_name = resource_attrs.get('service.name', '')
        operation = span_data.get('name', '')

        return {
            'trace_id': trace_id[:32],
            'span_id': span_id[:16],
            'parent_span_id': parent_span_id[:16] if parent_span_id else None,
            'service_name': service_name,
            'operation': operation,
            'start_time': start_time,
            'duration_ms': duration_ms,
            'status': status,
            'error_message': error_message,
            'attributes': {**resource_attrs, **attributes},
        }
    except Exception as e:
        logger.debug(f"[OTLP] 解析Span失败: {e}")
        return None


def _extract_attr_value(attr: Dict) -> Any:
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


def _parse_otlp_timestamp(nano_str: str) -> datetime:
    try:
        nanos = int(nano_str)
        seconds = nanos // 1_000_000_000
        dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
        return dt.replace(tzinfo=None)
    except (ValueError, TypeError, OSError):
        return datetime.now()
