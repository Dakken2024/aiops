from django.urls import path
from . import views

urlpatterns = [
    # 集群与看板
    path('clusters/', views.cluster_list, name='k8s_cluster_list'),
    path('clusters/delete/<int:pk>/', views.cluster_delete, name='k8s_cluster_delete'),
    path('clusters/edit/<int:pk>/', views.cluster_edit, name='k8s_cluster_edit'),
    path('dashboard/', views.cluster_dashboard, name='k8s_cluster_dashboard'),
    path('dashboard/diagnose/', views.k8s_cluster_diagnose, name='k8s_cluster_diagnose'),

    # 资源
    path('nodes/', views.node_list, name='k8s_node_list'),
    path('nodes/diagnose/', views.k8s_node_diagnose, name='k8s_node_diagnose'),

    path('pods/', views.pod_list, name='k8s_pod_list'),
    path('pods/log/', views.get_pod_log, name='k8s_pod_log'),
    path('shell/<str:pod_name>/', views.pod_terminal, name='k8s_pod_terminal'),
    path('diagnose/', views.k8s_diagnose, name='k8s_diagnose'),
    # 节点详情与更新
    path('nodes/details/<str:node_name>/', views.node_details, name='k8s_node_details'),
    path('nodes/update/', views.node_update, name='k8s_node_update'),
    #运维操作
    path('nodes/cordon/', views.node_cordon, name='k8s_node_cordon'),
    path('nodes/drain/', views.node_drain, name='k8s_node_drain'),
    path('nodes/delete/', views.node_delete, name='k8s_node_delete'),
    path('nodes/candidates/', views.node_candidates, name='k8s_node_candidates'),
    path('nodes/add/', views.node_add_execute, name='k8s_node_add'),
    path('nodes/task_status/', views.node_task_status, name='k8s_node_task_status'),  # <--- 新增
    path('nodes/get_token/', views.node_get_token, name='k8s_node_get_token'),

    path('deployments/', views.deployment_list, name='k8s_deployment_list'),
    path('deployments/scale/', views.deployment_scale, name='k8s_deployment_scale'),

    path('daemonsets/', views.daemonset_list, name='k8s_daemonset_list'),
    path('statefulsets/', views.statefulset_list, name='k8s_statefulset_list'),

    path('services/', views.service_list, name='k8s_service_list'),
    path('ingresses/', views.ingress_list, name='k8s_ingress_list'),

    # 创建与分析
    path('create/', views.resource_create, name='k8s_resource_create'),
    path('analyze/', views.k8s_yaml_analyze, name='k8s_yaml_analyze'),
    # === Secret 管理 ===
    path('secrets/', views.secret_list, name='k8s_secret_list'),
    path('secrets/create/', views.secret_create, name='k8s_secret_create'),
    path('secrets/delete/', views.secret_delete, name='k8s_secret_delete'),
    path('secrets/detail/', views.secret_detail, name='k8s_secret_detail'),
    path('secrets/update/', views.secret_update, name='k8s_secret_update'),
    # === 工作负载详情与操作 ===
    path('workload/detail/', views.workload_detail, name='k8s_workload_detail'),
    path('workload/update_yaml/', views.workload_update_yaml, name='k8s_workload_update_yaml'),
    path('workload/restart/', views.workload_restart, name='k8s_workload_restart'),
    path('workload/describe/', views.workload_describe, name='k8s_workload_describe'),

    # === Helm 应用商店 ===
    path('helm/', views.helm_store_index, name='k8s_helm_store'),
    path('helm/repo/', views.helm_repo_api, name='k8s_helm_repo'),
    path('helm/chart/', views.helm_chart_api, name='k8s_helm_chart'),
    path('helm/release/', views.helm_release_api, name='k8s_helm_release'),

    # === 存储管理 ===
    path('storage/pvc/', views.pvc_list, name='k8s_pvc_list'),
    path('storage/pv/', views.pv_list, name='k8s_pv_list'),
    path('storage/sc/', views.storage_class_list, name='k8s_storage_class_list'),
    # === 操作接口 ===
    path('storage/pvc/create/', views.pvc_create, name='k8s_pvc_create'),
    path('storage/api/', views.storage_resource_api, name='k8s_storage_api'),
    # === cm管理 ===
    path('configmap/', views.configmap_list, name='k8s_configmap_list'),
    path('configmap/api/', views.configmap_api, name='k8s_configmap_api'),

    path('node/image_ops/', views.node_image_ops, name='k8s_node_image_ops'),
]