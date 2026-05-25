from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

# System API views
from system.api.views import CustomTokenObtainPairView, UserInfoView, WebhookEndpointViewSet

# CMDB API viewsets
from cmdb.api.views import (
    ServerGroupViewSet,
    ServerViewSet,
    CloudAccountViewSet,
    TerminalLogViewSet,
    ServerMetricViewSet,
    HighRiskAuditViewSet,
    CMDBCloudResourceViewSet,
    SSLCertificateViewSet
)

# Monitoring API viewsets
from monitoring.api.views import (
    AlertRuleViewSet,
    AlertEventViewSet,
    AlertSilenceRuleViewSet,
    AnomalyHistoryViewSet,
    AlertGroupViewSet,
    AlertCorrelationRuleViewSet,
    RemediationActionViewSet,
    RemediationHistoryViewSet,
    RunbookEntryViewSet,
    AgentTokenViewSet,
    ServiceTopologyViewSet,
    SavedDashboardViewSet,
    HealthScoreViewSet,
    MonitoringCloudResourceViewSet,
    DataRetentionPolicyViewSet,
    MetricAggregationViewSet,
    LogEntryViewSet,
    LogPatternViewSet,
    TraceSpanViewSet,
    WebhookEndpointViewSet,
    CaseVectorViewSet,
    MetricBaselineViewSet
)

# Prediction API viewsets
from prediction.api.views import (
    CapacityForecastViewSet,
    AnomalyDetectionViewSet,
    BaselineModelViewSet,
    ForecastAPIView,
    AnomalyAPIView,
    BaselineAPIView,
)

# Log Analysis API viewsets
from log_analysis.api.views import (
    LogSourceViewSet,
    LogEntryViewSet,
    LogPatternViewSet,
    LogAlertRuleViewSet,
    LogAlertViewSet,
    LogAnalysisViewSet,
)

# Create a router and register our viewsets with it
router = DefaultRouter()

# Register Log Analysis viewsets
router.register(r'log-analysis/sources', LogSourceViewSet, basename='log-analysis-source')
router.register(r'log-analysis/entries', LogEntryViewSet, basename='log-analysis-entry')
router.register(r'log-analysis/patterns', LogPatternViewSet, basename='log-analysis-pattern')
router.register(r'log-analysis/alert-rules', LogAlertRuleViewSet, basename='log-analysis-alert-rule')
router.register(r'log-analysis/alerts', LogAlertViewSet, basename='log-analysis-alert')
router.register(r'log-analysis/analysis', LogAnalysisViewSet, basename='log-analysis-analysis')

# Register CMDB viewsets
router.register(r'cmdb/server-groups', ServerGroupViewSet, basename='server-group')
router.register(r'cmdb/servers', ServerViewSet, basename='server')
router.register(r'cmdb/cloud-accounts', CloudAccountViewSet, basename='cloud-account')
router.register(r'cmdb/terminal-logs', TerminalLogViewSet, basename='terminal-log')
router.register(r'cmdb/server-metrics', ServerMetricViewSet, basename='server-metric')
router.register(r'cmdb/high-risk-audits', HighRiskAuditViewSet, basename='high-risk-audit')
router.register(r'cmdb/cloud-resources', CMDBCloudResourceViewSet, basename='cmdb-cloud-resource')
router.register(r'cmdb/ssl-certificates', SSLCertificateViewSet, basename='ssl-certificate')

# Register Monitoring viewsets
router.register(r'monitoring/alert-rules', AlertRuleViewSet, basename='alert-rule')
router.register(r'monitoring/alert-events', AlertEventViewSet, basename='alert-event')
router.register(r'monitoring/alert-silence-rules', AlertSilenceRuleViewSet, basename='alert-silence-rule')
router.register(r'monitoring/anomaly-histories', AnomalyHistoryViewSet, basename='anomaly-history')
router.register(r'monitoring/alert-groups', AlertGroupViewSet, basename='alert-group')
router.register(r'monitoring/alert-correlation-rules', AlertCorrelationRuleViewSet, basename='alert-correlation-rule')
router.register(r'monitoring/remediation-actions', RemediationActionViewSet, basename='remediation-action')
router.register(r'monitoring/remediation-histories', RemediationHistoryViewSet, basename='remediation-history')
router.register(r'monitoring/runbook-entries', RunbookEntryViewSet, basename='runbook-entry')
router.register(r'monitoring/agent-tokens', AgentTokenViewSet, basename='agent-token')
router.register(r'monitoring/service-topologies', ServiceTopologyViewSet, basename='service-topology')
router.register(r'monitoring/saved-dashboards', SavedDashboardViewSet, basename='saved-dashboard')
router.register(r'monitoring/health-scores', HealthScoreViewSet, basename='health-score')
router.register(r'monitoring/cloud-resources', MonitoringCloudResourceViewSet, basename='monitoring-cloud-resource')
router.register(r'monitoring/data-retention-policies', DataRetentionPolicyViewSet, basename='data-retention-policy')
router.register(r'monitoring/metric-aggregations', MetricAggregationViewSet, basename='metric-aggregation')
router.register(r'monitoring/log-entries', LogEntryViewSet, basename='log-entry')
router.register(r'monitoring/log-patterns', LogPatternViewSet, basename='log-pattern')
router.register(r'monitoring/trace-spans', TraceSpanViewSet, basename='trace-span')
router.register(r'monitoring/webhook-endpoints', WebhookEndpointViewSet, basename='webhook-endpoint')
router.register(r'monitoring/case-vectors', CaseVectorViewSet, basename='case-vector')
router.register(r'monitoring/metric-baselines', MetricBaselineViewSet, basename='metric-baseline')

# Register Prediction viewsets
router.register(r'prediction/capacity-forecasts', CapacityForecastViewSet, basename='capacity-forecast')
router.register(r'prediction/anomaly-detections', AnomalyDetectionViewSet, basename='anomaly-detection')
router.register(r'prediction/baseline-models', BaselineModelViewSet, basename='baseline-model')

# Register System viewsets
router.register(r'system/webhook-endpoints', WebhookEndpointViewSet, basename='system-webhook-endpoint')

urlpatterns = [
    # Prediction API endpoints
    path('prediction/capacity-forecast/', ForecastAPIView.capacity_forecast, name='prediction-capacity-forecast'),
    path('prediction/alert-forecast/', ForecastAPIView.alert_forecast, name='prediction-alert-forecast'),
    path('prediction/anomaly-detection/', AnomalyAPIView.anomaly_detection, name='prediction-anomaly-detection'),
    path('prediction/anomaly-stats/', AnomalyAPIView.anomaly_stats, name='prediction-anomaly-stats'),
    path('prediction/baseline-model/', BaselineAPIView.baseline_model, name='prediction-baseline-model'),
    path('prediction/baseline-for-server/<int:server_id>/', BaselineAPIView.baseline_for_server, name='prediction-baseline-for-server'),
    path('prediction/trigger-baseline-learning/', BaselineAPIView.trigger_baseline_learning, name='prediction-trigger-baseline-learning'),
    # JWT Authentication
    path('auth/login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/user/', UserInfoView.as_view(), name='user_info'),
    
    # API Router
    path('', include(router.urls)),
]

