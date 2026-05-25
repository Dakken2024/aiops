import re
import logging
from datetime import datetime
from typing import List, Dict, Optional

import paramiko

logger = logging.getLogger(__name__)

SYSLOG_PRIORITY_MAP = {
    0: 'EMERG', 1: 'ALERT', 2: 'CRIT', 3: 'ERROR',
    4: 'WARN', 5: 'NOTICE', 6: 'INFO', 7: 'DEBUG',
}

SYSLOG_REGEX = re.compile(
    r'<(?P<priority>\d+)>(?P<timestamp>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+'
    r'(?P<hostname>\S+)\s+(?P<program>\S+?)(?:\[(?P<pid>\d+)\])?:\s*(?P<message>.*)'
)

SIMPLE_LOG_REGEX = re.compile(
    r'(?P<timestamp>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})\s+'
    r'(?:\[(?P<level>\w+)\]\s+)?(?P<message>.*)'
)


class SSHLogCollector:
    LOG_PATHS = [
        '/var/log/syslog', '/var/log/messages',
        '/var/log/auth.log', '/var/log/secure',
    ]

    def __init__(self, server):
        self.server = server

    def collect(self, log_path: Optional[str] = None, lines: int = 100) -> List[Dict]:
        path = log_path or self._detect_log_path()
        if not path:
            return []

        command = f'tail -n {lines} {path} 2>/dev/null'
        output = self._execute_ssh(command)
        if not output:
            return []

        return self._parse_log_lines(output)

    def _detect_log_path(self) -> Optional[str]:
        command = 'ls /var/log/syslog /var/log/messages 2>/dev/null | head -1'
        output = self._execute_ssh(command)
        return output.strip() if output else None

    def _execute_ssh(self, command: str) -> Optional[str]:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            connect_kwargs = {
                'hostname': self.server.ip_address,
                'port': self.server.port,
                'username': self.server.username,
                'timeout': 15,
            }
            if self.server.password:
                connect_kwargs['password'] = self.server.password
            client.connect(**connect_kwargs)
            _, stdout, _ = client.exec_command(command, timeout=30)
            return stdout.read().decode('utf-8', errors='replace')
        except Exception as e:
            logger.debug(f"[SSHLogCollector] {self.server.hostname}: {e}")
            return None
        finally:
            client.close()

    def _parse_log_lines(self, raw: str) -> List[Dict]:
        results = []
        for line in raw.strip().split('\n'):
            if not line.strip():
                continue
            parsed = self._parse_single_line(line)
            if parsed:
                results.append(parsed)
        return results

    def _parse_single_line(self, line: str) -> Optional[Dict]:
        m = SYSLOG_REGEX.match(line)
        if m:
            priority = int(m.group('priority'))
            level = SYSLOG_PRIORITY_MAP.get(priority % 8, 'INFO')
            ts_str = m.group('timestamp')
            try:
                year = datetime.now().year
                ts = datetime.strptime(f"{year} {ts_str}", "%Y %b %d %H:%M:%S")
            except ValueError:
                ts = datetime.now()
            return {
                'timestamp': ts,
                'level': level,
                'source': m.group('program'),
                'message': m.group('message'),
                'structured_data': {
                    'hostname': m.group('hostname'),
                    'pid': m.group('pid'),
                    'priority': priority,
                },
            }

        m2 = SIMPLE_LOG_REGEX.match(line)
        if m2:
            level = m2.group('level') or 'INFO'
            level = level.upper()
            if level not in ['ERROR', 'WARN', 'INFO', 'DEBUG', 'CRIT', 'EMERG', 'ALERT', 'NOTICE']:
                level = 'INFO'
            try:
                ts = datetime.fromisoformat(m2.group('timestamp').replace(' ', 'T'))
            except ValueError:
                ts = datetime.now()
            return {
                'timestamp': ts,
                'level': level,
                'source': 'application',
                'message': m2.group('message'),
                'structured_data': {},
            }

        return {
            'timestamp': datetime.now(),
            'level': 'INFO',
            'source': 'unknown',
            'message': line[:500],
            'structured_data': {},
        }
