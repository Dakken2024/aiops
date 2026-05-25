import socket
import logging
import re
from datetime import datetime
from threading import Thread

from django.conf import settings

logger = logging.getLogger(__name__)

SYSLOG_REGEX = re.compile(
    r'<(?P<priority>\d+)>(?P<timestamp>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+'
    r'(?P<hostname>\S+)\s+(?P<program>\S+?)(?:\[(?P<pid>\d+)\])?:\s*(?P<message>.*)'
)

PRIORITY_MAP = {
    0: 'EMERG', 1: 'ALERT', 2: 'CRIT', 3: 'ERROR',
    4: 'WARN', 5: 'NOTICE', 6: 'INFO', 7: 'DEBUG',
}


class SyslogUDPReceiver:
    def __init__(self, host='0.0.0.0', port=5140):
        self.host = host
        self.port = port
        self._running = False
        self._socket = None

    def start(self):
        self._running = True
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.settimeout(1.0)
        self._socket.bind((self.host, self.port))
        logger.info(f"[SyslogUDP] 监听 {self.host}:{self.port}")

        thread = Thread(target=self._listen, daemon=True)
        thread.start()

    def stop(self):
        self._running = False
        if self._socket:
            self._socket.close()

    def _listen(self):
        while self._running:
            try:
                data, addr = self._socket.recvfrom(65535)
                message = data.decode('utf-8', errors='replace').strip()
                if message:
                    self._process_message(message, addr[0])
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logger.debug(f"[SyslogUDP] 接收异常: {e}")

    def _process_message(self, raw_message: str, source_ip: str):
        from monitoring.models import LogEntry
        from cmdb.models import Server

        parsed = self._parse_syslog(raw_message)
        if not parsed:
            return

        try:
            server = Server.objects.filter(ip_address=source_ip).first()
            if not server:
                return

            LogEntry.objects.create(
                server=server,
                timestamp=parsed['timestamp'],
                level=parsed['level'],
                source=parsed.get('program', 'syslog'),
                message=parsed['message'],
                structured_data={'hostname': parsed.get('hostname', ''), 'pid': parsed.get('pid', '')},
            )
        except Exception as e:
            logger.debug(f"[SyslogUDP] 处理失败: {e}")

    def _parse_syslog(self, message: str):
        m = SYSLOG_REGEX.match(message)
        if not m:
            return None

        priority = int(m.group('priority'))
        level = PRIORITY_MAP.get(priority % 8, 'INFO')
        ts_str = m.group('timestamp')
        try:
            year = datetime.now().year
            ts = datetime.strptime(f"{year} {ts_str}", "%Y %b %d %H:%M:%S")
        except ValueError:
            ts = datetime.now()

        return {
            'timestamp': ts,
            'level': level,
            'hostname': m.group('hostname'),
            'program': m.group('program'),
            'pid': m.group('pid'),
            'message': m.group('message'),
        }
