from rest_framework import viewsets, filters, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework import serializers
from django.utils import timezone
from datetime import timedelta
from celery.result import AsyncResult

from log_analysis.models import LogSource, LogEntry, LogPattern, LogAlertRule, LogAlert
from log_analysis import tasks
from log_analysis.collectors import SyslogCollector, FileCollector

import logging

logger = logging.getLogger(__name__)


class LogSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = LogSource
        fields = '__all__'


class LogEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LogEntry
        fields = '__all__'


class LogPatternSerializer(serializers.ModelSerializer):
    class Meta:
        model = LogPattern
        fields = '__all__'


class LogAlertRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = LogAlertRule
        fields = '__all__'


class LogAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = LogAlert
        fields = '__all__'


class LogSourceViewSet(viewsets.ModelViewSet):
    queryset = LogSource.objects.all()
    serializer_class = LogSourceSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'type']
    
    @action(detail=True, methods=['post'])
    def start_collector(self, request, pk=None):
        log_source = self.get_object()
        if not log_source.is_enabled:
            return Response({'error': '日志源未启用'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            if log_source.type == 'syslog':
                collector = SyslogCollector(log_source)
            elif log_source.type == 'file':
                collector = FileCollector(log_source)
            else:
                return Response({'error': '不支持的日志类型'}, status=status.HTTP_400_BAD_REQUEST)
            
            collector.start()
            return Response({'status': 'started', 'message': f'{log_source.name} 采集器已启动'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LogEntryViewSet(viewsets.ModelViewSet):
    queryset = LogEntry.objects.all()
    serializer_class = LogEntrySerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['message', 'level']
    
    @action(detail=False, methods=['get'])
    def recent_errors(self, request):
        hours = int(request.query_params.get('hours', 24))
        start_time = timezone.now() - timedelta(hours=hours)
        logs = LogEntry.objects.filter(
            timestamp__gte=start_time,
            level__in=['error', 'critical', 'warning']
        ).order_by('-timestamp')[:100]
        serializer = self.get_serializer(logs, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def by_source(self, request):
        source_id = request.query_params.get('source_id')
        if not source_id:
            return Response({'error': 'source_id 参数缺失'}, status=status.HTTP_400_BAD_REQUEST)
        logs = LogEntry.objects.filter(source_id=source_id).order_by('-timestamp')[:100]
        serializer = self.get_serializer(logs, many=True)
        return Response(serializer.data)


class LogPatternViewSet(viewsets.ModelViewSet):
    queryset = LogPattern.objects.all()
    serializer_class = LogPatternSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['pattern', 'description']


class LogAlertRuleViewSet(viewsets.ModelViewSet):
    queryset = LogAlertRule.objects.all()
    serializer_class = LogAlertRuleSerializer
    
    @action(detail=False, methods=['post'])
    def test_rule(self, request):
        rule_id = request.data.get('rule_id')
        log_message = request.data.get('log_message')
        
        if not rule_id or not log_message:
            return Response({'error': '缺少参数'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            rule = LogAlertRule.objects.get(id=rule_id)
            matched = False
            
            if rule.level_filter:
                levels = [l.strip().lower() for l in rule.level_filter.split(',')]
                matched = any(kw.lower() in log_message.lower() for kw in levels)
            
            if rule.trigger_type == 'keyword' and rule.keywords:
                matched = any(kw.lower() in log_message.lower() for kw in rule.keywords)
            
            return Response({'matched': matched, 'rule_name': rule.name})
        except LogAlertRule.DoesNotExist:
            return Response({'error': '规则不存在'}, status=status.HTTP_404_NOT_FOUND)


class LogAlertViewSet(viewsets.ModelViewSet):
    queryset = LogAlert.objects.all()
    serializer_class = LogAlertSerializer
    
    @action(detail=True, methods=['post'])
    def acknowledge(self, request, pk=None):
        alert = self.get_object()
        alert.status = 'acknowledged'
        alert.acknowledged_at = timezone.now()
        alert.save()
        return Response({'status': 'acknowledged'})
    
    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        alert = self.get_object()
        alert.status = 'resolved'
        alert.resolved_at = timezone.now()
        alert.save()
        return Response({'status': 'resolved'})


class LogAnalysisViewSet(viewsets.GenericViewSet):
    @action(detail=False, methods=['post'])
    def generate_summary(self, request):
        hours = request.data.get('hours', 24)
        log_entry_ids = request.data.get('log_entry_ids')
        
        task = tasks.ai_log_summary.delay(log_entry_ids=log_entry_ids, hours=hours)
        return Response({'task_id': task.task_id, 'status': 'processing'})
    
    @action(detail=False, methods=['get'])
    def summary_status(self, request):
        task_id = request.query_params.get('task_id')
        if not task_id:
            return Response({'error': 'task_id 参数缺失'}, status=status.HTTP_400_BAD_REQUEST)
        
        result = AsyncResult(task_id)
        return Response({
            'task_id': task_id,
            'status': result.status,
            'result': result.result if result.ready() else None
        })
    
    @action(detail=False, methods=['post'])
    def check_alerts(self, request):
        result = tasks.check_log_alerts.delay()
        return Response({'task_id': result.task_id, 'status': 'processing'})