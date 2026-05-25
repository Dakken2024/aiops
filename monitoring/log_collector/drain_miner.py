import re
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)


class DrainLogMiner:
    def __init__(self, sim_threshold=0.5, max_children=100):
        self.sim_threshold = sim_threshold
        self.max_children = max_children
        self.log_clusters = {}

    def mine(self, log_entries: List[Dict]) -> List[Dict]:
        for entry in log_entries:
            message = entry.get('message', '')
            if not message:
                continue
            tokens = self._tokenize(message)
            if not tokens:
                continue
            cluster_id = self._find_cluster(tokens)
            if cluster_id is not None:
                self._update_cluster(cluster_id, entry)
            else:
                self._create_cluster(tokens, entry)

        results = []
        for cid, cluster in self.log_clusters.items():
            results.append({
                'pattern_id': cid,
                'pattern_template': cluster['template'],
                'level': cluster['level'],
                'source': cluster['source'],
                'occurrence_count': cluster['count'],
                'first_seen': cluster['first_seen'],
                'last_seen': cluster['last_seen'],
                'is_anomaly': cluster.get('is_anomaly', False),
            })
        return results

    def _tokenize(self, message: str) -> List[str]:
        message = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '<IP>', message)
        message = re.sub(r'\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}\b', '<TIMESTAMP>', message)
        message = re.sub(r'\b0x[0-9a-fA-F]+\b', '<HEX>', message)
        message = re.sub(r'\b\d+\.?\d*\b', '<NUM>', message)
        message = re.sub(r'\b[a-f0-9]{8,}\b', '<ID>', message)
        message = re.sub(r'/[\w./\-]+', '<PATH>', message)
        return message.split()

    def _find_cluster(self, tokens: List[str]) -> Optional[int]:
        best_id = None
        best_sim = self.sim_threshold

        for cid, cluster in self.log_clusters.items():
            template_tokens = cluster['template'].split()
            sim = self._similarity(tokens, template_tokens)
            if sim > best_sim:
                best_sim = sim
                best_id = cid

        return best_id

    def _similarity(self, tokens1: List[str], tokens2: List[str]) -> float:
        if not tokens1 or not tokens2:
            return 0.0
        if abs(len(tokens1) - len(tokens2)) > max(len(tokens1), len(tokens2)) * 0.5:
            return 0.0
        min_len = min(len(tokens1), len(tokens2))
        match_count = sum(1 for i in range(min_len) if tokens1[i] == tokens2[i])
        return match_count / max(len(tokens1), len(tokens2))

    def _update_cluster(self, cluster_id: int, entry: Dict):
        cluster = self.log_clusters[cluster_id]
        cluster['count'] += 1
        cluster['last_seen'] = entry.get('timestamp', datetime.now())
        template_tokens = cluster['template'].split()
        new_tokens = self._tokenize(entry.get('message', ''))
        min_len = min(len(template_tokens), len(new_tokens))
        updated = []
        for i in range(min_len):
            if template_tokens[i] == new_tokens[i]:
                updated.append(template_tokens[i])
            else:
                updated.append('*')
        cluster['template'] = ' '.join(updated)

    def _create_cluster(self, tokens: List[str], entry: Dict):
        cid = len(self.log_clusters)
        self.log_clusters[cid] = {
            'template': ' '.join(tokens),
            'level': entry.get('level', 'INFO'),
            'source': entry.get('source', 'syslog'),
            'count': 1,
            'first_seen': entry.get('timestamp', datetime.now()),
            'last_seen': entry.get('timestamp', datetime.now()),
            'is_anomaly': False,
        }


def detect_anomaly_patterns(patterns: List[Dict], baseline_window: int = 7) -> List[Dict]:
    now = datetime.now()
    for pattern in patterns:
        if pattern['occurrence_count'] > 10:
            pattern['is_anomaly'] = True
        elif pattern['level'] in ('ERROR', 'CRIT', 'ALERT', 'EMERG') and pattern['occurrence_count'] > 3:
            pattern['is_anomaly'] = True
    return patterns
