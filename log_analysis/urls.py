from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api.views import (
    LogSourceViewSet,
    LogEntryViewSet,
    LogPatternViewSet,
    LogAlertRuleViewSet,
    LogAlertViewSet,
    LogAnalysisViewSet,
)

router = DefaultRouter()
router.register(r'sources', LogSourceViewSet)
router.register(r'entries', LogEntryViewSet)
router.register(r'patterns', LogPatternViewSet)
router.register(r'alert-rules', LogAlertRuleViewSet)
router.register(r'alerts', LogAlertViewSet)
router.register(r'analysis', LogAnalysisViewSet, basename='analysis')

urlpatterns = [
    path('', include(router.urls)),
]