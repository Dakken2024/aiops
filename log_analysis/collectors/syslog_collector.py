import socket
import logging
import re
from datetime import datetime
from threading import Thread
from django.conf import settings

logger = logging.getLogger(__name__)

SYSLOG_REGEX = re.compile(
    r'<(?P<priority>\d+)>(?P<version>\d+)?\s*'
    r'(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))?\s*'
    r'(?P<hostname>\S+)?\s*'
    r'(?P<app_name>\S+)?\s*'
    r'(?P<proc_id>\S+)?\s*'
    r'(?P<msg_id>\S+)?\s*'
    r'(?:\[(?P<structured_data>[^\]]+)\])?\s*'
    r'(?P<message>.*)'
)

LEGACY_SYSLOG_REGEX = re.compile(
    r'<(?P<priority>\d+)>(?P<timestamp>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+'
    r'(?P<hostname>\S+)\s+'
    r'(?P<program>\S+?)(?:\[(?P<pid>\d+)\])?:\s*(?P<message>.*)'
)

PRIORITY_MAP = {
    0: 'emerg', 1: 'alert', 2: 'critical', 3: 'error',
    4: 'warning', 5: 'notice', 6: 'info', 7: 'debug',
}


class SyslogCollector:
    def __init__(self, log_source):
        self.log_source = log_source
        self.config = log_source.config
        self.host = self.config.get('host', '0.0.0.0')
        self.port = self.config.get('port', 514)
        self.protocol = self.config.get('protocol', 'udp').lower()
        self._running = False
        self._socket = None
        self._thread = None

    def start(self):
        self._running = True
        
        if self.protocol == 'udp':
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.settimeout(1.0)
        elif self.protocol == 'tcp':
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        else:
            logger.error(f"不支持的协议: {self.protocol}")
            return

        try:
            self._socket.bind((self.host, self.port))
            logger.info(f"[SyslogCollector] 开始监听 {self.protocol.upper()}://{self.host}:{self.port}")
        except Exception as e:
            logger.error(f"[SyslogCollector] 绑定失败: {e}")
            return

        if self.protocol == 'tcp':
            self._socket.listen(5)
        
        self._thread = Thread(target=self._listen, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._socket:
            try:
                self._socket.close()
            except:
                pass
        if self._thread:
            self._thread.join(timeout=2)

    def _listen(self):
        if self.protocol == 'udp':
            self._listen_udp()
        else:
            self._listen_tcp()

    def _listen_udp(self):
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
                    logger.debug(f"[SyslogCollector] UDP接收异常: {e}")

    def _listen_tcp(self):
        while self._running:
            try:
                self._socket.settimeout(1.0)
                conn, addr = self._socket.accept()
                conn.settimeout(30.0)
                
                buffer = ''
                while self._running:
                    try:
                        data = conn.recv(4096)
                        if not data:
                            break
                        buffer += data.decode('utf-8', errors='replace')
                        
                        while '\n' in buffer:
                            line, buffer = buffer.split('\n', 1)
                            line = line.strip()
                            if line:
                                self._process_message(line, addr[0])
                    except socket.timeout:
                        break
                conn.close()
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logger.debug(f"[SyslogCollector] TCP接收异常: {e}")

    def _process_message(self, raw_message: str, source_ip: str):
        from log_analysis.models import LogEntry, LogPattern, LogSource
        from cmdb.models import Server

        parsed = self._parse_syslog(raw_message)
        if not parsed:
            return

        try:
            server = Server.objects.filter(ip_address=source_ip).first()
            
            log_entry = LogEntry.objects.create(
                source=self.log_source,
                server=server,
                timestamp=parsed['timestamp'],
                level=parsed['level'],
                message=parsed['message'],
                parsed_data={
                    'hostname': parsed.get('hostname', ''),
                    'program': parsed.get('program', ''),
                    'pid': parsed.get('pid', ''),
                    'app_name': parsed.get('app_name', ''),
                }
            )
            
            self._match_pattern(log_entry)
            
        except Exception as e:
            logger.debug(f"[SyslogCollector] 处理失败: {e}")

    def _parse_syslog(self, message: str):
        m = SYSLOG_REGEX.match(message)
        if m:
            priority = int(m.group('priority'))
            level = PRIORITY_MAP.get(priority % 8, 'info')
            
            ts_str = m.group('timestamp')
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                except ValueError:
                    ts = datetime.now()
            else:
                ts = datetime.now()

            return {
                'timestamp': ts,
                'level': level,
                'hostname': m.group('hostname'),
                'app_name': m.group('app_name'),
                'program': m.group('app_name') or m.group('proc_id'),
                'pid': m.group('proc_id'),
                'message': m.group('message'),
            }
        
        m = LEGACY_SYSLOG_REGEX.match(message)
        if m:
            priority = int(m.group('priority'))
            level = PRIORITY_MAP.get(priority % 8, 'info')
            
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
        
        return None

    def _match_pattern(self, log_entry: 'LogEntry'):
        patterns = LogPattern.objects.all()
        for pattern in patterns:
            try:
                if re.search(pattern.pattern, log_entry.message):
                    log_entry.pattern = pattern
                    log_entry.save()
                    
                    pattern.occurrences += 1
                    pattern.last_seen = datetime.now()
                    pattern.save()
                    break
            except re.error:
                continue