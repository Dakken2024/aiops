from django.urls import path
from tracing.api.views import otlp_receiver, trace_detail, trace_list, service_list

urlpatterns = [
    path('otlp/v1/traces/', otlp_receiver, name='otlp_receiver'),
    path('traces/', trace_list, name='trace_list'),
    path('traces/<str:trace_id>/', trace_detail, name='trace_detail'),
    path('services/', service_list, name='service_list'),
]
