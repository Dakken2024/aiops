from django.urls import path
from . import views

urlpatterns = [
    # === 1. AI 模型管理 (配置 Key) ===
    path('models/', views.model_list, name='model_list'),
    path('models/delete/<int:pk>/', views.model_delete, name='model_delete'),

    # === 2. 智能运维功能 (诊断 & 审计) ===
    path('diagnose/<int:server_id>/', views.diagnose_server, name='diagnose_server'),
    path('audit/<int:log_id>/', views.audit_terminal_log, name='audit_terminal_log'),

    # === 新增：WebSSH 命令生成接口 ===
    path('chat/command/', views.generate_command, name='generate_command'),
    path('chat/explain/', views.explain_log, name='explain_log'),
    # === 新增：高危命令评估 ===
    path('assess_risk/', views.assess_risk, name='assess_risk'),
]