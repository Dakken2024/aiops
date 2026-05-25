import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Count, Q
from datetime import timedelta

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from prediction.models import CapacityForecast, AlertForecast, AnomalyDetection, BaselineModel
from cmdb.models import Server


def paginate_queryset(qs, request, default_size=20):
    page = max(1, int(request.GET.get('page', 1)))
    page_size = min(100, max(1, int(request.GET.get('page_size', default_size))))
    total = qs.count()
    start = (page - 1) * page_size
    end = start + page_size
    items = qs[start:end]
    return items, {'total': total, 'page': page, 'page_size': page_size}


class ForecastAPIView:
    @staticmethod
    @login_required
    @require_GET
    def capacity_forecast(request):
        server_id = request.GET.get('server_id')
        metric_type = request.GET.get('metric_type', '')
        
        qs = CapacityForecast.objects.select_related('server')
        
        if server_id:
            try:
                qs = qs.filter(server_id=int(server_id))
            except ValueError:
                return JsonResponse({'code': 1, 'msg': '无效的server_id'}, status=400)
        
        if metric_type:
            qs = qs.filter(metric_type=metric_type)
        
        qs = qs.order_by('-forecast_date')
        items, pagination = paginate_queryset(qs, request)
        
        data = [{
            'id': cf.id,
            'server_id': cf.server.id,
            'server_hostname': cf.server.hostname,
            'server_ip': cf.server.ip_address,
            'metric_type': cf.metric_type,
            'metric_type_display': cf.get_metric_type_display(),
            'forecast_date': cf.forecast_date.isoformat(),
            'forecast_data': cf.forecast_data,
            'confidence': round(cf.confidence, 4),
            'created_at': cf.created_at.isoformat(),
        } for cf in items]
        
        return JsonResponse({'code': 0, 'data': {'items': data, **pagination}})
    
    @staticmethod
    @login_required
    @require_GET
    def alert_forecast(request):
        rule_id = request.GET.get('rule_id')
        
        qs = AlertForecast.objects.select_related('rule')
        
        if rule_id:
            try:
                qs = qs.filter(rule_id=int(rule_id))
            except ValueError:
                return JsonResponse({'code': 1, 'msg': '无效的rule_id'}, status=400)
        
        qs = qs.order_by('-predicted_time')
        items, pagination = paginate_queryset(qs, request)
        
        data = [{
            'id': af.id,
            'rule_id': af.rule.id,
            'rule_name': af.rule.name,
            'rule_severity': af.rule.severity,
            'predicted_count': af.predicted_count,
            'predicted_time': af.predicted_time.isoformat(),
            'created_at': af.created_at.isoformat(),
        } for af in items]
        
        return JsonResponse({'code': 0, 'data': {'items': data, **pagination}})


class AnomalyAPIView:
    @staticmethod
    @login_required
    @require_GET
    def anomaly_detection(request):
        server_id = request.GET.get('server_id')
        severity = request.GET.get('severity', '')
        hours = int(request.GET.get('hours', 24))
        
        qs = AnomalyDetection.objects.select_related('server')
        
        if server_id:
            try:
                qs = qs.filter(server_id=int(server_id))
            except ValueError:
                return JsonResponse({'code': 1, 'msg': '无效的server_id'}, status=400)
        
        if severity:
            qs = qs.filter(severity=severity)
        
        cutoff = timezone.now() - timedelta(hours=hours)
        qs = qs.filter(detected_at__gte=cutoff).order_by('-detected_at')
        
        items, pagination = paginate_queryset(qs, request)
        
        data = [{
            'id': ad.id,
            'server_id': ad.server.id if ad.server else None,
            'server_hostname': ad.server.hostname if ad.server else None,
            'server_ip': ad.server.ip_address if ad.server else None,
            'detected_at': ad.detected_at.isoformat(),
            'score': round(ad.score, 4),
            'severity': ad.severity,
            'severity_display': ad.get_severity_display(),
            'metric_name': ad.metric_name,
            'method_used': ad.method_used,
            'features': ad.features,
            'created_at': ad.created_at.isoformat(),
        } for ad in items]
        
        return JsonResponse({'code': 0, 'data': {'items': data, **pagination}})
    
    @staticmethod
    @login_required
    @require_GET
    def anomaly_stats(request):
        hours = int(request.GET.get('hours', 24))
        cutoff = timezone.now() - timedelta(hours=hours)
        
        stats = {
            'total': AnomalyDetection.objects.filter(detected_at__gte=cutoff).count(),
            'by_severity': dict(
                AnomalyDetection.objects.filter(detected_at__gte=cutoff)
                .values('severity')
                .annotate(cnt=Count('id'))
                .values_list('severity', 'cnt')
            ),
            'by_method': dict(
                AnomalyDetection.objects.filter(detected_at__gte=cutoff)
                .values('method_used')
                .annotate(cnt=Count('id'))
                .values_list('method_used', 'cnt')
            ),
        }
        
        return JsonResponse({'code': 0, 'data': stats})


class BaselineAPIView:
    @staticmethod
    @login_required
    @require_GET
    def baseline_model(request):
        server_id = request.GET.get('server_id')
        metric_type = request.GET.get('metric_type', '')
        
        qs = BaselineModel.objects.select_related('server')
        
        if server_id:
            try:
                qs = qs.filter(server_id=int(server_id))
            except ValueError:
                return JsonResponse({'code': 1, 'msg': '无效的server_id'}, status=400)
        
        if metric_type:
            qs = qs.filter(metric_type=metric_type)
        
        items, pagination = paginate_queryset(qs, request)
        
        data = [{
            'id': bm.id,
            'server_id': bm.server.id,
            'server_hostname': bm.server.hostname,
            'server_ip': bm.server.ip_address,
            'metric_type': bm.metric_type,
            'metric_type_display': bm.get_metric_type_display(),
            'baseline_data': bm.baseline_data,
            'learned_periods': bm.learned_periods,
            'last_learned_at': bm.last_learned_at.isoformat() if bm.last_learned_at else None,
            'created_at': bm.created_at.isoformat(),
            'updated_at': bm.updated_at.isoformat(),
        } for bm in items]
        
        return JsonResponse({'code': 0, 'data': {'items': data, **pagination}})
    
    @staticmethod
    @login_required
    @require_GET
    def baseline_for_server(request, server_id):
        try:
            server = Server.objects.get(id=server_id)
        except Server.DoesNotExist:
            return JsonResponse({'code': 1, 'msg': '服务器不存在'}, status=404)
        
        metric_type = request.GET.get('metric_type', '')
        qs = BaselineModel.objects.filter(server=server)
        
        if metric_type:
            qs = qs.filter(metric_type=metric_type)
        
        baselines = list(qs)
        
        data = [{
            'id': bm.id,
            'metric_type': bm.metric_type,
            'metric_type_display': bm.get_metric_type_display(),
            'baseline_data': bm.baseline_data,
            'learned_periods': bm.learned_periods,
            'last_learned_at': bm.last_learned_at.isoformat() if bm.last_learned_at else None,
        } for bm in baselines]
        
        return JsonResponse({
            'code': 0,
            'data': {
                'server_id': server.id,
                'server_hostname': server.hostname,
                'server_ip': server.ip_address,
                'baselines': data,
            }
        })
    
    @staticmethod
    @login_required
    @require_POST
    def trigger_baseline_learning(request):
        from prediction.tasks import baseline_learning
        result = baseline_learning.delay()
        return JsonResponse({'code': 0, 'data': {'task_id': result.task_id}})


class CapacityForecastViewSet(viewsets.ModelViewSet):
    queryset = CapacityForecast.objects.select_related('server').order_by('-forecast_date')
    serializer_class = None
    permission_classes = [permissions.IsAuthenticated]
    
    def list(self, request):
        server_id = request.query_params.get('server_id')
        metric_type = request.query_params.get('metric_type')
        
        qs = self.queryset
        
        if server_id:
            qs = qs.filter(server_id=server_id)
        if metric_type:
            qs = qs.filter(metric_type=metric_type)
        
        items, pagination = paginate_queryset(qs, request)
        
        data = [{
            'id': cf.id,
            'server_id': cf.server.id,
            'server_hostname': cf.server.hostname,
            'metric_type': cf.metric_type,
            'forecast_date': cf.forecast_date.isoformat(),
            'forecast_data': cf.forecast_data,
            'confidence': cf.confidence,
        } for cf in items]
        
        return Response({'items': data, **pagination})


class AnomalyDetectionViewSet(viewsets.ModelViewSet):
    queryset = AnomalyDetection.objects.select_related('server').order_by('-detected_at')
    serializer_class = None
    permission_classes = [permissions.IsAuthenticated]
    
    def list(self, request):
        server_id = request.query_params.get('server_id')
        severity = request.query_params.get('severity')
        
        qs = self.queryset
        
        if server_id:
            qs = qs.filter(server_id=server_id)
        if severity:
            qs = qs.filter(severity=severity)
        
        items, pagination = paginate_queryset(qs, request)
        
        data = [{
            'id': ad.id,
            'server_id': ad.server.id if ad.server else None,
            'server_hostname': ad.server.hostname if ad.server else None,
            'detected_at': ad.detected_at.isoformat(),
            'score': ad.score,
            'severity': ad.severity,
            'metric_name': ad.metric_name,
            'method_used': ad.method_used,
        } for ad in items]
        
        return Response({'items': data, **pagination})


class BaselineModelViewSet(viewsets.ModelViewSet):
    queryset = BaselineModel.objects.select_related('server')
    serializer_class = None
    permission_classes = [permissions.IsAuthenticated]
    
    def list(self, request):
        server_id = request.query_params.get('server_id')
        metric_type = request.query_params.get('metric_type')
        
        qs = self.queryset
        
        if server_id:
            qs = qs.filter(server_id=server_id)
        if metric_type:
            qs = qs.filter(metric_type=metric_type)
        
        items, pagination = paginate_queryset(qs, request)
        
        data = [{
            'id': bm.id,
            'server_id': bm.server.id,
            'server_hostname': bm.server.hostname,
            'metric_type': bm.metric_type,
            'baseline_data': bm.baseline_data,
            'learned_periods': bm.learned_periods,
            'last_learned_at': bm.last_learned_at.isoformat() if bm.last_learned_at else None,
        } for bm in items]
        
        return Response({'items': data, **pagination})