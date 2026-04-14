from django.urls import path
from . import views

urlpatterns = [
    # 页面路由
    path('list/', views.script_list, name='script_list'),
    path('create/', views.script_edit, name='script_create'),
    path('edit/<int:script_id>/', views.script_edit, name='script_edit'),

    # AJAX 接口路由
    path('api/', views.script_api, name='script_api'),

    path('task/create/<int:script_id>/', views.task_create, name='task_create'),
    path('task/submit/', views.task_submit_api, name='task_submit'),
    path('task/detail/<int:task_id>/', views.task_detail, name='task_detail'),
    path('task/result/', views.task_result_api, name='task_result_api'),
    path('task/log/', views.task_log_content, name='task_log_content'),

    path('api/script_ai/', views.script_ai_api, name='script_ai_api'),
    path('task/history/', views.task_list, name='task_list'),
]