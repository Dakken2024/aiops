from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import viewsets, permissions, serializers
from rest_framework.decorators import action
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.utils import timezone
from system.models import User, WebhookEndpoint, WebhookLog
from system.tasks.webhook_tasks import compute_hmac_signature


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'phone', 'department', 'is_active', 'is_staff']


class CustomTokenObtainPairSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        username = attrs.get('username')
        password = attrs.get('password')

        user = authenticate(username=username, password=password)
        if not user:
            raise serializers.ValidationError('用户名或密码错误')
        if not user.is_active:
            raise serializers.ValidationError('用户已被禁用')

        refresh = RefreshToken.for_user(user)
        
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': UserSerializer(user).data
        }


class CustomTokenObtainPairView(APIView):
    """自定义登录视图，返回 Token 和用户信息"""
    def post(self, request, *args, **kwargs):
        serializer = CustomTokenObtainPairSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class CustomTokenRefreshView(TokenRefreshView):
    """Token 刷新视图"""
    pass


class UserInfoView(APIView):
    """获取当前登录用户信息"""
    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


class WebhookEndpointSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookEndpoint
        fields = ['id', 'name', 'url', 'method', 'headers', 'secret', 'enabled', 'events', 
                  'created_at', 'updated_at', 'last_status', 'last_sent_at']
        read_only_fields = ['id', 'created_at', 'updated_at', 'last_status', 'last_sent_at']


class WebhookLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookLog
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'sent_at']


class WebhookEndpointViewSet(viewsets.ModelViewSet):
    """
    Webhook 端点管理 ViewSet
    
    提供 Webhook 端点的 CRUD 操作和测试功能。
    支持的事件类型: alert_triggered, report_generated, anomaly_detected
    """
    queryset = WebhookEndpoint.objects.all()
    serializer_class = WebhookEndpointSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=True, methods=['post'], url_path='test')
    def test(self, request, pk=None):
        """
        测试 Webhook 端点
        
        发送测试事件到目标端点，验证配置是否正确。
        """
        endpoint = self.get_object()
        
        import requests
        import json
        
        # 构建测试数据
        test_payload = {
            'test': True,
            'message': 'Webhook 测试消息',
            'timestamp': timezone.now().isoformat(),
        }
        
        body_data = {
            'event_type': 'test',
            'timestamp': timezone.now().isoformat(),
            'payload': test_payload,
        }
        body_str = json.dumps(body_data, ensure_ascii=False)
        
        # 计算签名
        signature = compute_hmac_signature(endpoint.secret, body_str)
        if signature:
            body_data['signature'] = signature
        
        headers = {
            'Content-Type': 'application/json',
        }
        headers.update(endpoint.headers or {})
        if signature:
            headers['X-Webhook-Signature'] = f'sha256={signature}'
        
        try:
            response = requests.request(
                method=endpoint.method,
                url=endpoint.url,
                data=json.dumps(body_data, ensure_ascii=False),
                headers=headers,
                timeout=10,
            )
            
            success = 200 <= response.status_code < 300
            
            # 更新端点状态
            endpoint.last_status = str(response.status_code) if success else f'error_{response.status_code}'
            endpoint.last_sent_at = timezone.now()
            endpoint.save()
            
            return Response({
                'success': success,
                'status_code': response.status_code,
                'response_body': response.text[:500],
                'message': '测试成功' if success else '测试失败',
            })
        
        except requests.RequestException as e:
            endpoint.last_status = 'error'
            endpoint.last_sent_at = timezone.now()
            endpoint.save()
            
            return Response({
                'success': False,
                'error': str(e),
                'message': '请求失败',
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'], url_path='logs')
    def logs(self, request, pk=None):
        """获取端点的发送日志"""
        endpoint = self.get_object()
        logs = WebhookLog.objects.filter(endpoint=endpoint).order_by('-created_at')[:50]
        serializer = WebhookLogSerializer(logs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='event-types')
    def event_types(self, request):
        """获取支持的事件类型列表"""
        return Response({
            'event_types': [
                {
                    'name': 'alert_triggered',
                    'description': '告警触发时',
                },
                {
                    'name': 'report_generated',
                    'description': '报告生成时',
                },
                {
                    'name': 'anomaly_detected',
                    'description': '异常检测到时',
                },
            ]
        })

    def perform_create(self, serializer):
        """创建时自动生成签名密钥（如果未提供）"""
        instance = serializer.save()
        if not instance.secret:
            import secrets
            instance.secret = secrets.token_hex(32)
            instance.save()

