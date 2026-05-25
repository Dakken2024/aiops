import os
import re
import logging
from datetime import datetime
from threading import Thread
from time import sleep

logger = logging.getLogger(__name__)

LOG_LEVELS = {
    'DEBUG': 'debug',
    'INFO': 'info',
    'WARN': 'warning',
    'WARNING': 'warning',
    'ERROR': 'error',
    'CRITICAL': 'critical',
    'FATAL': 'critical',
}

class FileCollector:
    def __init__(self, log_source):
        self.log_source = log_source
        self.config = log_source.config
        self.file_path = self.config.get('file_path', '')
        self.poll_interval = self.config.get('poll_interval', 5)
        self.encoding = self.config.get('encoding', 'utf-8')
        self._running = False
        self._thread = None
        self._file_handle = None
        self._last_position = 0

    def start(self):
        if not self.file_path or not os.path.exists(self.file_path):
            logger.error(f"[FileCollector] 文件不存在: {self.file_path}")
            return

        self._running = True
        self._thread = Thread(target=self._watch, daemon=True)
        self._thread.start()
        logger.info(f"[FileCollector] 开始监控文件: {self.file_path}")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self._file_handle:
            try:
                self._file_handle.close()
            except:
                pass

    def _watch(self):
        while self._running:
            try:
                if not os.path.exists(self.file_path):
                    sleep(self.poll_interval)
                    continue

                if not self._file_handle:
                    self._open_file()

                self._read_new_lines()
                sleep(self.poll_interval)
            except Exception as e:
                logger.debug(f"[FileCollector] 监控异常: {e}")
                if self._file_handle:
                    try:
                        self._file_handle.close()
                    except:
                        pass
                    self._file_handle = None
                sleep(self.poll_interval)

    def _open_file(self):
        try:
            self._file_handle = open(self.file_path, 'r', encoding=self.encoding)
            self._file_handle.seek(0, os.SEEK_END)
            self._last_position = self._file_handle.tell()
        except Exception as e:
            logger.error(f"[FileCollector] 打开文件失败: {e}")

    def _read_new_lines(self):
        if not self._file_handle:
            return

        try:
            current_size = os.path.getsize(self.file_path)
            
            if current_size < self._last_position:
                self._file_handle.seek(0)
                self._last_position = 0
            
            self._file_handle.seek(self._last_position)
            lines = self._file_handle.readlines()
            
            for line in lines:
                line = line.strip()
                if line:
                    self._process_line(line)
            
            self._last_position = self._file_handle.tell()
        except Exception as e:
            logger.debug(f"[FileCollector] 读取失败: {e}")

    def _process_line(self, line: str):
        from log_analysis.models import LogEntry, LogPattern
        from cmdb.models import Server

        parsed = self._parse_log_line(line)
        if not parsed:
            return

        try:
            server = None
            server_name = self.config.get('server_name', '')
            if server_name:
                server = Server.objects.filter(hostname=server_name).first()

            log_entry = LogEntry.objects.create(
                source=self.log_source,
                server=server,
                timestamp=parsed['timestamp'],
                level=parsed['level'],
                message=parsed['message'],
                parsed_data=parsed.get('parsed_data', {})
            )

            self._match_pattern(log_entry)
            
        except Exception as e:
            logger.debug(f"[FileCollector] 处理失败: {e}")

    def _parse_log_line(self, line: str):
        patterns = [
            r'^(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+'
            r'\[(?P<level>[A-Z]+)\]\s+'
            r'(?P<message>.*)',
            
            r'^(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))\s+'
            r'(?P<level>[A-Z]+)\s+'
            r'(?P<message>.*)',
            
            r'^\[(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]\s+'
            r'(?P<level>[A-Z]+)\s+'
            r'(?P<message>.*)',
            
            r'^(?P<timestamp>\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})\s+'
            r'(?P<level>[A-Z]+)\s+'
            r'(?P<message>.*)',
        ]

        for pattern in patterns:
            m = re.match(pattern, line)
            if m:
                ts_str = m.group('timestamp')
                try:
                    ts = self._parse_timestamp(ts_str)
                except:
                    ts = datetime.now()

                level = LOG_LEVELS.get(m.group('level'), 'info')
                
                return {
                    'timestamp': ts,
                    'level': level,
                    'message': m.group('message'),
                    'parsed_data': {},
                }

        return {
            'timestamp': datetime.now(),
            'level': 'info',
            'message': line,
            'parsed_data': {},
        }

    def _parse_timestamp(self, ts_str: str):
        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M:%S.%f',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%S.%f',
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%dT%H:%M:%S.%fZ',
            '%Y-%m-%dT%H:%M:%S+00:00',
            '%d/%m/%Y %H:%M:%S',
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(ts_str, fmt)
            except ValueError:
                continue
        
        return datetime.now()

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