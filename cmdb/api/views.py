import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Count, Q
from datetime import timedelta

from rest_framework import viewsets, permissions
from rest_framework.response import Response
from cmdb.models import CloudResource, CloudAccount, Server, ServerMetric, ServerGroup, TerminalLog, HighRiskAudit, SSLCertificate


def paginate_queryset(qs, request, default_size=20):
    page = max(1, int(request.GET.get('page', 1)))
    page_size = min(100, max(1, int(request.GET.get('page_size', default_size))))
    total = qs.count()
    start = (page - 1) * page_size
    end = start + page_size
    items = qs[start:end]
    return items, {'total': total, 'page': page, 'page_size': page_size}


@login_required
@require_GET
def api_cloud_resources(request):
    """
    CloudResourceAPIView: 云资源列表接口
    支持按 provider/region/resource_type 筛选
    """
    qs = CloudResource.objects.select_related('cloud_account', 'local_server').all()
    
    provider = request.GET.get('provider')
    region = request.GET.get('region')
    resource_type = request.GET.get('resource_type')
    
    if provider:
        qs = qs.filter(provider=provider)
    if region:
        qs = qs.filter(region__icontains=region)
    if resource_type:
        qs = qs.filter(resource_type=resource_type)
    
    items, pagination = paginate_queryset(qs, request)
    
    data = [{
        'id': r.id,
        'provider': r.provider,
        'get_provider_display': r.get_provider_display(),
        'resource_type': r.resource_type,
        'get_resource_type_display': r.get_resource_type_display(),
        'instance_id': r.instance_id,
        'instance_name': r.instance_name,
        'region': r.region,
        'cloud_account_name': r.cloud_account.name,
        'local_server_name': r.local_server.hostname if r.local_server else '',
        'last_sync_at': r.last_sync_at.isoformat() if r.last_sync_at else None,
        'extra_config': r.extra_config,
    } for r in items]
    
    return JsonResponse({'code': 0, 'data': {'items': data, **pagination}})


@login_required
@require_GET
def api_cloud_resource_detail(request, pk):
    """
    CloudResourceAPIView: 云资源详情接口
    """
    try:
        resource = CloudResource.objects.select_related('cloud_account', 'local_server').get(id=pk)
        data = {
            'id': resource.id,
            'provider': resource.provider,
            'get_provider_display': resource.get_provider_display(),
            'resource_type': resource.resource_type,
            'get_resource_type_display': resource.get_resource_type_display(),
            'instance_id': resource.instance_id,
            'instance_name': resource.instance_name,
            'region': resource.region,
            'cloud_account': {
                'id': resource.cloud_account.id,
                'name': resource.cloud_account.name,
                'type': resource.cloud_account.type,
            },
            'local_server': {
                'id': resource.local_server.id,
                'hostname': resource.local_server.hostname,
                'ip_address': resource.local_server.ip_address,
            } if resource.local_server else None,
            'extra_config': resource.extra_config,
            'last_sync_at': resource.last_sync_at.isoformat() if resource.last_sync_at else None,
            'created_at': resource.created_at.isoformat(),
            'updated_at': resource.updated_at.isoformat(),
        }
        return JsonResponse({'code': 0, 'data': data})
    except CloudResource.DoesNotExist:
        return JsonResponse({'code': 1, 'msg': '云资源不存在'}, status=404)


@login_required
@require_GET
def api_cloud_resource_options(request):
    """
    获取云资源筛选选项（provider/region/resource_type）
    """
    providers = list(CloudResource.objects.values_list('provider', flat=True).distinct())
    regions = list(CloudResource.objects.values_list('region', flat=True).distinct())
    resource_types = list(CloudResource.objects.values_list('resource_type', flat=True).distinct())
    
    provider_labels = dict(CloudResource.PROVIDER_CHOICES)
    type_labels = dict(CloudResource.RESOURCE_TYPE_CHOICES)
    
    return JsonResponse({
        'code': 0,
        'data': {
            'providers': [{'value': p, 'label': provider_labels.get(p, p)} for p in providers if p],
            'regions': [{'value': r, 'label': r} for r in regions if r],
            'resource_types': [{'value': t, 'label': type_labels.get(t, t)} for t in resource_types if t],
        }
    })


# ==================== DRF ViewSets ====================

from rest_framework import serializers

class ServerGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServerGroup
        fields = '__all__'

class ServerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Server
        fields = '__all__'

class CloudAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = CloudAccount
        fields = '__all__'

class TerminalLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = TerminalLog
        fields = '__all__'

class ServerMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServerMetric
        fields = '__all__'

class HighRiskAuditSerializer(serializers.ModelSerializer):
    class Meta:
        model = HighRiskAudit
        fields = '__all__'

class CMDBCloudResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = CloudResource
        fields = '__all__'

class SSLCertificateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SSLCertificate
        fields = '__all__'


class ServerGroupViewSet(viewsets.ModelViewSet):
    queryset = ServerGroup.objects.all()
    serializer_class = ServerGroupSerializer
    permission_classes = [permissions.IsAuthenticated]

class ServerViewSet(viewsets.ModelViewSet):
    queryset = Server.objects.all()
    serializer_class = ServerSerializer
    permission_classes = [permissions.IsAuthenticated]

class CloudAccountViewSet(viewsets.ModelViewSet):
    queryset = CloudAccount.objects.all()
    serializer_class = CloudAccountSerializer
    permission_classes = [permissions.IsAuthenticated]

class TerminalLogViewSet(viewsets.ModelViewSet):
    queryset = TerminalLog.objects.all()
    serializer_class = TerminalLogSerializer
    permission_classes = [permissions.IsAuthenticated]

class ServerMetricViewSet(viewsets.ModelViewSet):
    queryset = ServerMetric.objects.all()
    serializer_class = ServerMetricSerializer
    permission_classes = [permissions.IsAuthenticated]

class HighRiskAuditViewSet(viewsets.ModelViewSet):
    queryset = HighRiskAudit.objects.all()
    serializer_class = HighRiskAuditSerializer
    permission_classes = [permissions.IsAuthenticated]

class CMDBCloudResourceViewSet(viewsets.ModelViewSet):
    queryset = CloudResource.objects.all()
    serializer_class = CMDBCloudResourceSerializer
    permission_classes = [permissions.IsAuthenticated]

class SSLCertificateViewSet(viewsets.ModelViewSet):
    queryset = SSLCertificate.objects.all()
    serializer_class = SSLCertificateSerializer
    permission_classes = [permissions.IsAuthenticated]
