import json
import gzip
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

METRIC_NAME_MAP = {
    'cpu_usage': 'cpu_usage',
    'memory_usage': 'mem_usage',
    'disk_usage': 'disk_usage',
    'load1': 'load_1min',
    'network_receive': 'net_in',
    'network_transmit': 'net_out',
}


def _decompress_body(body_bytes: bytes) -> bytes:
    try:
        import snappy
        return snappy.decompress(body_bytes)
    except ImportError:
        pass
    except Exception:
        pass

    try:
        return gzip.decompress(body_bytes)
    except Exception:
        pass

    return body_bytes


def parse_remote_write(body_bytes: bytes) -> List[Dict[str, Any]]:
    decompressed = _decompress_body(body_bytes)
    results = []

    try:
        from prometheus_remote_write_pb2 import WriteRequest
        wr = WriteRequest()
        wr.ParseFromString(decompressed)
        for ts in wr.timeseries:
            labels = {l.name: l.value for l in ts.labels}
            metric_name = labels.get('__name__', '')
            instance = labels.get('instance', '')
            mapped_field = METRIC_NAME_MAP.get(metric_name)
            if not mapped_field:
                continue
            for sample in ts.samples:
                ts_value = sample.timestamp
                ts_seconds = ts_value / 1000 if ts_value > 0 else 0
                try:
                    dt = datetime.fromtimestamp(ts_seconds, tz=timezone.utc).replace(tzinfo=None)
                except (ValueError, OSError):
                    dt = datetime.now()
                results.append({
                    'server_identifier': instance,
                    'metric_name': mapped_field,
                    'value': float(sample.value),
                    'timestamp': dt,
                })
    except ImportError:
        logger.debug("[RemoteWrite] protobuf module not available, skipping protobuf parse")
    except Exception as e:
        logger.debug(f"[RemoteWrite] protobuf parse failed: {e}")

    return results


def parse_remote_write_json(body_bytes: bytes) -> List[Dict[str, Any]]:
    try:
        data = json.loads(body_bytes)
    except (json.JSONDecodeError, TypeError):
        return []

    results = []
    timeseries = data.get('timeseries', [])

    for ts in timeseries:
        labels = ts.get('labels', {})
        metric_name = labels.get('__name__', '')
        instance = labels.get('instance', '')

        mapped_field = METRIC_NAME_MAP.get(metric_name)
        if not mapped_field:
            continue

        for sample in ts.get('values', []):
            if len(sample) < 2:
                continue
            ts_value = sample[0]
            value = sample[1]

            if isinstance(ts_value, (int, float)):
                ts_seconds = ts_value / 1000 if ts_value > 1e12 else ts_value
                try:
                    dt = datetime.fromtimestamp(ts_seconds, tz=timezone.utc).replace(tzinfo=None)
                except (ValueError, OSError):
                    dt = datetime.now()
            else:
                dt = datetime.now()

            results.append({
                'server_identifier': instance,
                'metric_name': mapped_field,
                'value': float(value),
                'timestamp': dt,
            })

    return results
