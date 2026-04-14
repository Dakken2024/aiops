import yaml,json,os,datetime
import subprocess
import tempfile
import shutil
from cmdb.models import Server
from cmdb.views import get_secure_ssh_client
from django.shortcuts import render, redirect, get_object_or_404
from kubernetes import client as k8s_client
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponseForbidden
# 引入工具和模型
from django.contrib import messages
from .utils import get_k8s_client, get_java_thread_dump, get_node_events
from .models import K8sCluster, NodeSnapshot
from ai_ops.models import AIModel
from ai_ops.utils import ask_ai
from collections import Counter
from django.db.models import Avg
from cmdb.models import ServerGroup, ServerGroupAuth
import paramiko
import logging,yaml
from ops_platform.celery import app as celery_app
from .tasks import k8s_node_add_task
from django.core.cache import cache
from celery.result import AsyncResult
from cmdb.models import Server
import base64
from kubernetes import client
from .models import ConfigMapHistory

# ==========================================
# 辅助函数：配置 YAML 输出格式
# ==========================================
def setup_custom_yaml():
    """
    配置 PyYAML使其对多行字符串使用 '|' 风格 (Block Style)
    这样 Nginx 配置显示就是整洁的多行，而不是一行带 \n 的字符串
    """
    def str_presenter(dumper, data):
        if '\n' in data:  # 如果字符串包含换行符，强制使用 | 风格
            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
        return dumper.represent_scalar('tag:yaml.org,2002:str', data)

    try:
        yaml.add_representer(str, str_presenter)
        # 防止 OrderedDict 报错 (如果是从 k8s client 获取的对象)
        yaml.add_representer(str, str_presenter, Dumper=yaml.SafeDumper)
    except:
        pass
# ==========================================
# 通用辅助: 获取 K8s 上下文
# ==========================================
def get_common_context(request):
    """
    获取 Client, Cluster, Namespaces, AI Models
    """
    cluster_id = request.GET.get('cluster_id')
    namespace = request.GET.get('namespace')
    visible_clusters = get_user_clusters(request.user)
    current_cluster = None
    if not cluster_id and visible_clusters.exists():
        cluster_id = visible_clusters.first().id
    if cluster_id:
            # 使用 filter(...).first() 确保只能查到权限范围内的
        current_cluster = visible_clusters.filter(id=cluster_id).first()

    core_v1 = apps_v1 = net_v1 = None
    err = None
    # get_k8s_client 返回: (CoreV1, AppsV1, NetworkingV1, error, cluster_obj)
    if current_cluster:
        core_v1, apps_v1, net_v1, err, _ = get_k8s_client(current_cluster.id)
    else:
        if visible_clusters.exists():
            err = "请选择集群"
        else:
            err = "无可见集群权限"
    namespaces = []
    if core_v1:
        try:
            ns_list = core_v1.list_namespace().items
            namespaces = [ns.metadata.name for ns in ns_list]
        except:
            pass

    return {
        'core_v1': core_v1,
        'apps_v1': apps_v1,
        'net_v1': net_v1,
        'error': err,
        'current_cluster': current_cluster,
        'clusters': visible_clusters,
        'namespaces': namespaces,
        'current_namespace': namespace,
        'ai_models': AIModel.objects.all()
    }


# ==========================================
# 1. 集群全景看板 (Dashboard) & AI 诊断
# ==========================================
login_required


def cluster_dashboard(request):
    # 1. 获取上下文 (Context)
    ctx = get_common_context(request)
    if ctx['error']:
        return render(request, 'k8s/cluster_dashboard.html', ctx)

    cluster = ctx['current_cluster']

    # === 优化点：定义缓存 Key (按集群ID隔离) ===
    cache_key = f"k8s_dashboard_stats_{cluster.id}"

    # 2. 尝试从缓存获取数据
    cached_data = cache.get(cache_key)
    if cached_data:
        # 如果缓存命中，合并 ctx 并直接返回
        # 注意：ctx 中的 core_v1 等客户端对象不能缓存，但统计数据可以
        ctx.update(cached_data)
        return render(request, 'k8s/cluster_dashboard.html', ctx)

    # 3. 缓存未命中，执行实时查询 (耗时逻辑)
    core_v1 = ctx['core_v1']
    apps_v1 = ctx['apps_v1']

    try:
        # === (原有逻辑保持不变) ===
        # A. 节点统计
        nodes = core_v1.list_node().items
        node_stats = {
            'total': len(nodes),
            'ready': sum(1 for n in nodes if any(c.type == 'Ready' and c.status == 'True' for c in n.status.conditions))
        }
        node_stats['not_ready'] = node_stats['total'] - node_stats['ready']

        # B. 资源水位 (DB查询)
        snapshots = NodeSnapshot.objects.filter(cluster_token=cluster.token)
        usage_stats = snapshots.aggregate(avg_cpu=Avg('cpu_usage'), avg_mem=Avg('mem_usage'))
        usage_data = {
            'cpu': round(usage_stats['avg_cpu'] or 0, 1),
            'mem': round(usage_stats['avg_mem'] or 0, 1)
        }

        # C. Pod 统计 (最耗时)
        all_pods = core_v1.list_pod_for_all_namespaces().items
        pod_phases = [p.status.phase for p in all_pods]
        pod_stats = dict(Counter(pod_phases))

        # D. Workloads
        deps = apps_v1.list_deployment_for_all_namespaces().items
        deploy_stats = {
            'total': len(deps),
            'ready': sum(1 for d in deps if d.status.ready_replicas == d.spec.replicas)
        }

        stss = apps_v1.list_stateful_set_for_all_namespaces().items
        sts_stats = {
            'total': len(stss),
            'ready': sum(1 for s in stss if s.status.ready_replicas == s.spec.replicas)
        }

        # E. 组件健康度
        comp_map = {}
        target_components = ['kube-apiserver', 'kube-controller-manager', 'kube-scheduler', 'etcd', 'coredns']
        sys_pods = core_v1.list_namespaced_pod('kube-system').items
        for name in target_components:
            matched_pods = [p for p in sys_pods if name in p.metadata.name]
            status = 'Healthy' if matched_pods and all(
                p.status.phase == 'Running' for p in matched_pods) else 'Unhealthy'
            comp_map[name] = status

        # F. 告警事件
        events = core_v1.list_event_for_all_namespaces(limit=20).items
        events.sort(key=lambda x: x.last_timestamp or x.event_time or x.metadata.creation_timestamp, reverse=True)
        warnings = [e for e in events if e.type != 'Normal'][:10]

        # 4. 构建需要缓存的数据字典
        stats_data = {
            'node_stats': node_stats,
            'usage': usage_data,
            'pod_stats': pod_stats,
            'total_pods': len(all_pods),
            'deploy_stats': deploy_stats,
            'sts_stats': sts_stats,
            'components': comp_map,
            'warnings': warnings
        }

        # === 优化点：写入缓存 (有效期 30 秒) ===
        cache.set(cache_key, stats_data, 30)

        # 更新上下文
        ctx.update(stats_data)

    except Exception as e:
        ctx['error'] = f"Dashboard Load Error: {str(e)}"

    return render(request, 'k8s/cluster_dashboard.html', ctx)


@login_required
@csrf_exempt
def k8s_cluster_diagnose(request):
    """[AJAX] AI 集群全景诊断"""
    if request.method != 'POST': return JsonResponse({'status': False})

    v1, _, _, err, _ = get_k8s_client(request.POST.get('cluster_id'))
    if err: return JsonResponse({'status': False, 'msg': err})

    try:
        nodes = v1.list_node().items
        not_ready = [n.metadata.name for n in nodes if
                     not any(c.type == 'Ready' and c.status == 'True' for c in n.status.conditions)]

        sys_pods = v1.list_namespaced_pod('kube-system').items
        bad_pods = [f"{p.metadata.name}({p.status.phase})" for p in sys_pods if p.status.phase != 'Running']

        events = v1.list_event_for_all_namespaces(limit=50).items
        warns = list(set([f"[{e.involved_object.kind}:{e.involved_object.name}] {e.reason}" for e in events if
                          e.type == 'Warning']))[:15]

        prompt = f"""
        作为 K8s 架构师进行集群体检。
        【节点】异常: {not_ready if not_ready else "无"}
        【组件】异常(kube-system): {bad_pods if bad_pods else "无"}
        【告警】近期 Warning: {warns if warns else "无"}

        请分析：1. 健康评分(0-100) 2. 潜在风险 3. 运维建议。
        """
        res = ask_ai(prompt, model_id=request.POST.get('model_id'), system_role="K8s Architect")
        return JsonResponse({'status': True, 'analysis': res.get('content', 'AI无响应')})
    except Exception as e:
        return JsonResponse({'status': False, 'msg': str(e)})


# ==========================================
# 2. 节点管理 & Agent 上报 & 节点诊断
# ==========================================
@login_required
def node_list(request):
    ctx = get_common_context(request)
    if ctx['error']: return render(request, 'k8s/node_list.html', ctx)
    try:
        nodes = ctx['core_v1'].list_node().items
        data = []
        for n in nodes:
            is_unschedulable = n.spec.unschedulable if n.spec.unschedulable else False
            status = "NotReady"
            reason = ""
            for c in n.status.conditions:
                if c.type == "Ready":
                    if c.status == "True":
                        status = "Ready"
                    else:
                        reason = c.message

            ip = "-"
            for addr in n.status.addresses:
                if addr.type == "InternalIP": ip = addr.address

            data.append({
                'name': n.metadata.name, 'status': status, 'ip': ip,
                'role': 'Master' if 'node-role.kubernetes.io/control-plane' in n.metadata.labels else 'Worker',
                'version': n.status.node_info.kubelet_version,
                'os': n.status.node_info.os_image,
                'age': n.metadata.creation_timestamp,
                'reason': reason,
                'unschedulable': is_unschedulable,
            })
        ctx['nodes'] = data
    except Exception as e:
        ctx['error'] = str(e)
    return render(request, 'k8s/node_list.html', ctx)

@login_required
@csrf_exempt
def k8s_node_diagnose(request):
    """[AI] 节点诊断 (API状态 + Agent日志)"""
    if request.method != 'POST': return JsonResponse({'status': False})

    cluster_id = request.POST.get('cluster_id')
    node_name = request.POST.get('node_name')

    v1, _, _, err, cluster = get_k8s_client(cluster_id)
    if not v1: return JsonResponse({'status': False, 'msg': err})

    try:
        # A. K8s 状态
        node = v1.read_node(node_name)
        conds = "\n".join([f"{c.type}={c.status} ({c.message})" for c in node.status.conditions])
        events = get_node_events(v1, node_name)

        # B. Agent 日志
        try:
            snap = NodeSnapshot.objects.filter(cluster_token=cluster.token, node_name=node_name).first()
            os_logs = f"[Res] CPU:{snap.cpu_usage}% Disk:{snap.disk_usage}%\n[Kubelet]:\n{snap.kubelet_log[-1500:]}\n[Proxy]:\n{snap.proxy_log[-800:]}" if snap else "无Agent数据"
        except:
            os_logs = "读取Agent失败"

        prompt = f"诊断K8s节点故障。\nNode:{node_name}\n【K8s状态】:\n{conds}\n【Events】:\n{events}\n【底层日志】:\n{os_logs}\n请分析NotReady原因并给出修复命令。"

        res = ask_ai(prompt, model_id=request.POST.get('model_id'), system_role="K8s Expert")
        if 'error' in res: return JsonResponse({'status': False, 'msg': res['error']})
        return JsonResponse({'status': True, 'analysis': res['content']})
    except Exception as e:
        return JsonResponse({'status': False, 'msg': str(e)})


# ==========================================
# 3. Pod 管理 (列表, 诊断, 日志, Shell)
# ==========================================
@login_required
def pod_list(request):
    ctx = get_common_context(request)
    if ctx['error']: return render(request, 'k8s/pod_list.html', ctx)
    try:
        ns = ctx['current_namespace']
        items = ctx['core_v1'].list_namespaced_pod(ns).items if ns else ctx[
            'core_v1'].list_pod_for_all_namespaces().items
        data = []
        for p in items:
            status = p.status.phase
            restarts = 0
            reason = ""
            if p.status.container_statuses:
                for c in p.status.container_statuses:
                    restarts += c.restart_count
                    if c.last_state.terminated:
                        if c.last_state.terminated.reason == "OOMKilled":
                            status, reason = "OOMKilled", "内存溢出"
                        elif c.last_state.terminated.reason != "Completed":
                            reason = c.last_state.terminated.reason
            data.append({'name': p.metadata.name, 'namespace': p.metadata.namespace, 'ip': p.status.pod_ip,
                         'node': p.spec.node_name, 'status': status, 'restarts': restarts,
                         'age': p.metadata.creation_timestamp, 'reason': reason})
        ctx['pods'] = data
    except Exception as e:
        ctx['error'] = str(e)
    return render(request, 'k8s/pod_list.html', ctx)


@login_required
@csrf_exempt
def k8s_diagnose(request):
    """[AI] Pod 诊断"""
    if request.method != 'POST': return JsonResponse({'status': False})
    v1, _, _, err, _ = get_k8s_client(request.POST.get('cluster_id'))
    if err: return JsonResponse({'status': False, 'msg': err})

    pod, ns = request.POST.get('pod_name'), request.POST.get('namespace')
    try:
        try:
            logs = v1.read_namespaced_pod_log(pod, ns, tail_lines=300)
        except:
            logs = "无日志"
        try:
            status = str(v1.read_namespaced_pod(pod, ns).status)
        except:
            status = "无状态"

        thread_dump = ""
        if "Running" in status:
            thread_dump = get_java_thread_dump(v1, pod, ns)

        prompt = f"诊断K8s Pod: {pod}\nStatus:{status[:800]}\nLog:{logs[-2000:]}\nStack:{thread_dump[:2000]}\n分析OOM/死锁/异常并建议。"
        res = ask_ai(prompt, model_id=request.POST.get('model_id'), system_role="K8s Expert")

        if 'error' in res: return JsonResponse({'status': False, 'msg': res['error']})
        return JsonResponse({'status': True, 'analysis': res['content']})
    except Exception as e:
        return JsonResponse({'status': False, 'msg': str(e)})


@login_required
@csrf_exempt
def get_pod_log(request):
    v1, _, _, err, _ = get_k8s_client(request.GET.get('cluster_id'))
    if err: return JsonResponse({'status': False, 'log': err})
    try:
        log = v1.read_namespaced_pod_log(request.GET.get('name'), request.GET.get('namespace'), tail_lines=500)
        return JsonResponse({'status': True, 'log': log})
    except Exception as e:
        return JsonResponse({'status': False, 'log': str(e)})


@login_required
def pod_terminal(request, pod_name):
    if not request.GET.get('cluster_id'): return HttpResponse("Missing cluster_id", status=400)
    return render(request, 'k8s/terminal.html', {
        'pod_name': pod_name, 'namespace': request.GET.get('namespace'), 'cluster_id': request.GET.get('cluster_id')
    })


# ==========================================
# 4. 工作负载 (Deploy, DS, STS)
# ==========================================
@login_required
def deployment_list(request):
    ctx = get_common_context(request)
    if ctx['error']: return render(request, 'k8s/deployment_list.html', ctx)
    try:
        ns = ctx['current_namespace']
        items = ctx['apps_v1'].list_namespaced_deployment(ns).items if ns else ctx[
            'apps_v1'].list_deployment_for_all_namespaces().items
        ctx['deployments'] = [{'name': d.metadata.name, 'namespace': d.metadata.namespace,
                               'ready': f"{d.status.ready_replicas or 0}/{d.spec.replicas}",
                               'replicas': d.spec.replicas, 'image': d.spec.template.spec.containers[0].image,
                               'age': d.metadata.creation_timestamp} for d in items]
    except Exception as e:
        ctx['error'] = str(e)
    return render(request, 'k8s/deployment_list.html', ctx)


@login_required
def daemonset_list(request):
    ctx = get_common_context(request)
    if ctx['error']: return render(request, 'k8s/daemonset_list.html', ctx)
    try:
        ns = ctx['current_namespace']
        items = ctx['apps_v1'].list_namespaced_daemon_set(ns).items if ns else ctx[
            'apps_v1'].list_daemon_set_for_all_namespaces().items
        ctx['daemonsets'] = [
            {'name': d.metadata.name, 'namespace': d.metadata.namespace, 'desired': d.status.desired_number_scheduled,
             'ready': d.status.number_ready, 'image': d.spec.template.spec.containers[0].image,
             'age': d.metadata.creation_timestamp} for d in items]
    except Exception as e:
        ctx['error'] = str(e)
    return render(request, 'k8s/daemonset_list.html', ctx)


@login_required
def statefulset_list(request):
    ctx = get_common_context(request)
    if ctx['error']: return render(request, 'k8s/statefulset_list.html', ctx)
    try:
        ns = ctx['current_namespace']
        items = ctx['apps_v1'].list_namespaced_stateful_set(ns).items if ns else ctx[
            'apps_v1'].list_stateful_set_for_all_namespaces().items
        ctx['statefulsets'] = [{'name': s.metadata.name, 'namespace': s.metadata.namespace,
                                'replicas': f"{s.status.ready_replicas or 0}/{s.spec.replicas}",
                                'image': s.spec.template.spec.containers[0].image, 'age': s.metadata.creation_timestamp}
                               for s in items]
    except Exception as e:
        ctx['error'] = str(e)
    return render(request, 'k8s/statefulset_list.html', ctx)


@login_required
@csrf_exempt
def deployment_scale(request):
    if request.method != 'POST': return JsonResponse({'status': False})
    _, apps_v1, _, err, _ = get_k8s_client(request.POST.get('cluster_id'))
    if err: return JsonResponse({'status': False, 'msg': err})
    try:
        apps_v1.patch_namespaced_deployment_scale(request.POST.get('name'), request.POST.get('namespace'),
                                                  {'spec': {'replicas': int(request.POST.get('replicas'))}})
        return JsonResponse({'status': True, 'msg': '扩缩容成功'})
    except Exception as e:
        return JsonResponse({'status': False, 'msg': str(e)})


# ==========================================
# 5. 集群配置 & YAML & 网络
# ==========================================
@login_required
def cluster_list(request):
    if request.method == 'POST':
        if not (request.user.is_superuser or request.user.has_perm('k8s_manager.add_k8scluster')):
            return HttpResponseForbidden()
        K8sCluster.objects.create(name=request.POST.get('name'), kubeconfig=request.POST.get('kubeconfig'))
        return redirect('k8s_cluster_list')
    return render(request, 'k8s/cluster_list.html', {'clusters': K8sCluster.objects.all()})


@login_required
def cluster_delete(request, pk):
    get_object_or_404(K8sCluster, pk=pk).delete()
    return redirect('k8s_cluster_list')


@login_required
def resource_create(request):
    ctx = get_common_context(request)

    if request.method == 'POST':
        yaml_content = request.POST.get('yaml_content')

        # === 修改点：优先从表单获取目标集群 ID ===
        target_cluster_id = request.POST.get('cluster_id')

        if target_cluster_id:
            # 如果前端选择了特定集群，重新获取该集群的 Client
            v1, _, _, err, target_cluster = get_k8s_client(target_cluster_id)
            if err:
                ctx['create_error'] = f"连接目标集群失败: {err}"
                return render(request, 'k8s/resource_create.html', ctx)
            # 更新上下文中的 current_cluster 以便页面回显正确状态
            ctx['current_cluster'] = target_cluster
        else:
            # 否则使用 URL 参数中的默认集群
            v1 = ctx['core_v1']

        if v1:
            try:
                from kubernetes import utils
                # 执行创建
                created_count = 0
                for obj in yaml.safe_load_all(yaml_content):
                    if obj:
                        utils.create_from_dict(v1.api_client, obj)
                        created_count += 1
                ctx['create_success'] = f"成功在 [{ctx['current_cluster'].name}] 创建 {created_count} 个资源"
            except Exception as e:
                ctx['create_error'] = f"创建失败: {str(e)}"
        else:
            ctx['create_error'] = "无法获取集群客户端，请检查集群配置"

    return render(request, 'k8s/resource_create.html', ctx)

@login_required
@csrf_exempt
def k8s_yaml_analyze(request):
    if request.method != 'POST': return JsonResponse({'status': False})
    res = ask_ai(f"审计YAML:\n{request.POST.get('yaml_content')}\n检查语法、安全、资源。", model_id=request.POST.get('model_id'),
                 system_role="K8s Auditor")
    if 'error' in res: return JsonResponse({'status': False, 'msg': res['error']})
    return JsonResponse({'status': True, 'analysis': res['content']})


@login_required
def service_list(request):
    ctx = get_common_context(request)
    if ctx['error']: return render(request, 'k8s/service_list.html', ctx)
    try:
        ns = ctx['current_namespace']
        items = ctx['core_v1'].list_namespaced_service(ns).items if ns else ctx[
            'core_v1'].list_service_for_all_namespaces().items
        ctx['services'] = [{'name': s.metadata.name, 'namespace': s.metadata.namespace, 'type': s.spec.type,
                            'cluster_ip': s.spec.cluster_ip,
                            'ports': ", ".join([f"{p.port}:{p.target_port}" for p in s.spec.ports]),
                            'age': s.metadata.creation_timestamp} for s in items]
    except Exception as e:
        ctx['error'] = str(e)
    return render(request, 'k8s/service_list.html', ctx)


@login_required
def ingress_list(request):
    ctx = get_common_context(request)
    if ctx['error']: return render(request, 'k8s/ingress_list.html', ctx)
    try:
        ns = ctx['current_namespace']
        items = ctx['net_v1'].list_namespaced_ingress(ns).items if ns else ctx[
            'net_v1'].list_ingress_for_all_namespaces().items
        data = []
        for i in items:
            rules = [f"{r.host} -> {[p.path for p in r.http.paths]}" for r in i.spec.rules] if i.spec.rules else []
            data.append({'name': i.metadata.name, 'namespace': i.metadata.namespace, 'rules': rules,
                         'age': i.metadata.creation_timestamp})
        ctx['ingresses'] = data
    except Exception as e:
        ctx['error'] = str(e)
    return render(request, 'k8s/ingress_list.html', ctx)


def get_user_clusters(user):
    """
    根据用户权限返回可见的 K8s 集群列表
    """
    if user.is_superuser:
        return K8sCluster.objects.all()

    # 1. 获取用户角色绑定的分组 ID
    my_role_ids = user.groups.values_list('id', flat=True)
    allowed_group_ids = ServerGroupAuth.objects.filter(
        role_id__in=my_role_ids
    ).values_list('server_group_id', flat=True)

    # 2. 过滤属于这些分组的集群
    # (注意：如果 cluster.group 为空，通常默认仅管理员可见，或者你可以决定是否让所有人可见)
    return K8sCluster.objects.filter(group_id__in=allowed_group_ids)


@login_required
def cluster_edit(request, pk):
    """编辑 K8s 集群 (用于修改分组或 KubeConfig)"""
    # 只有超级管理员可以管理集群配置
    if not request.user.is_superuser:
        return HttpResponse("Permission Denied", status=403)

    cluster = get_object_or_404(K8sCluster, pk=pk)

    if request.method == 'POST':
        cluster.name = request.POST.get('name')
        cluster.kubeconfig = request.POST.get('kubeconfig')

        # 更新分组
        group_id = request.POST.get('group_id')
        if group_id:
            cluster.group = ServerGroup.objects.get(id=group_id)
        else:
            cluster.group = None  # 设置为全局/未分组

        cluster.save()
        messages.success(request, f"集群 {cluster.name} 配置已更新")
        return redirect('k8s_cluster_list')

    # 获取所有分组供选择
    all_groups = ServerGroup.objects.all()

    return render(request, 'k8s/cluster_edit.html', {
        'cluster': cluster,
        'all_groups': all_groups
    })


# ==========================================
# 新增: 节点标签与污点管理
# ==========================================
@login_required
def node_details(request, node_name):
    """获取单个节点的 Labels 和 Taints 详情"""
    cluster_id = request.GET.get('cluster_id')
    v1, _, _, err, _ = get_k8s_client(cluster_id)
    if err: return JsonResponse({'status': False, 'msg': err})

    try:
        node = v1.read_node(node_name)
        # 处理 Labels
        labels = node.metadata.labels or {}

        # 处理 Taints
        taints = []
        if node.spec.taints:
            for t in node.spec.taints:
                taints.append({'key': t.key, 'value': t.value, 'effect': t.effect})

        return JsonResponse({'status': True, 'labels': labels, 'taints': taints})
    except Exception as e:
        return JsonResponse({'status': False, 'msg': str(e)})


@login_required
@csrf_exempt
def node_update(request):
    """更新节点的 Labels 和 Taints"""
    if request.method != 'POST':
        return JsonResponse({'status': False, 'msg': 'Method not allowed'})

    try:
        data = json.loads(request.body)
        cluster_id = data.get('cluster_id')
        node_name = data.get('node_name')
        new_labels = data.get('labels', {})
        new_taints_data = data.get('taints', [])

        v1, _, _, err, _ = get_k8s_client(cluster_id)
        if err: return JsonResponse({'status': False, 'msg': err})

        # 1. 获取当前节点对象
        node = v1.read_node(node_name)

        # 2. 更新 Labels (直接覆盖)
        node.metadata.labels = new_labels

        # 3. 更新 Taints
        # 需要将前端传来的字典列表转换为 V1Taint 对象列表
        taint_objs = []
        for t in new_taints_data:
            if t.get('key'):  # 过滤空key
                taint_objs.append(k8s_client.V1Taint(
                    key=t['key'],
                    value=t.get('value'),
                    effect=t.get('effect', 'NoSchedule')
                ))
        node.spec.taints = taint_objs

        # 4. 提交更新 (使用 replace_node 确保状态一致)
        v1.replace_node(node_name, node)

        return JsonResponse({'status': True})
    except Exception as e:
        return JsonResponse({'status': False, 'msg': str(e)})


# ==========================================
# 新增: 节点运维 (调度、排水、删除)
# ==========================================
@login_required
@csrf_exempt
def node_cordon(request):
    """[AJAX] 设置节点调度状态 (Cordon/Uncordon)"""
    if request.method != 'POST': return JsonResponse({'status': False})

    data = json.loads(request.body)
    cluster_id = data.get('cluster_id')
    node_name = data.get('node_name')
    unschedulable = data.get('unschedulable')  # Boolean: True=停止调度, False=恢复调度

    v1, _, _, err, _ = get_k8s_client(cluster_id)
    if err: return JsonResponse({'status': False, 'msg': err})

    try:
        body = {'spec': {'unschedulable': unschedulable}}
        v1.patch_node(node_name, body)
        action_str = "已停止调度 (Cordon)" if unschedulable else "已恢复调度 (Uncordon)"
        return JsonResponse({'status': True, 'msg': f'节点 {node_name} {action_str}'})
    except Exception as e:
        return JsonResponse({'status': False, 'msg': str(e)})



@login_required
@csrf_exempt
def node_drain(request):
    """[AJAX] 节点排水 (Cordon + Evict Pods)"""
    if request.method != 'POST': return JsonResponse({'status': False})

    data = json.loads(request.body)
    cluster_id = data.get('cluster_id')
    node_name = data.get('node_name')

    v1, _, _, err, _ = get_k8s_client(cluster_id)
    if err: return JsonResponse({'status': False, 'msg': err})

    try:
        # 1. 先停止调度
        v1.patch_node(node_name, {'spec': {'unschedulable': True}})

        # 2. 获取节点上的所有 Pod
        pods = v1.list_pod_for_all_namespaces(field_selector=f'spec.nodeName={node_name}').items

        evicted = 0
        skipped = 0
        errors = []

        for pod in pods:
            # 跳过 DaemonSet (它们由 DS 控制器管理，不需要驱逐)
            owner = pod.metadata.owner_references[0].kind if pod.metadata.owner_references else ""
            if owner == "DaemonSet":
                skipped += 1
                continue

            # [关键修复] 跳过静态 Pod (Mirror Pod)
            # pod.metadata.annotations 可能为 None，需要先处理为字典
            annotations = pod.metadata.annotations or {}
            if "kubernetes.io/config.source" in annotations:
                skipped += 1
                continue

            try:
                # 构建驱逐请求
                eviction = k8s_client.V1Eviction(
                    metadata=k8s_client.V1ObjectMeta(name=pod.metadata.name, namespace=pod.metadata.namespace)
                )
                v1.create_namespaced_pod_eviction(pod.metadata.name, pod.metadata.namespace, eviction)
                evicted += 1
            except Exception as e:
                # 忽略 "Cannot evict pod as it does not exist" 这类错误
                if "Not Found" not in str(e):
                    errors.append(f"{pod.metadata.name}: {str(e)}")

        msg = f"排水操作完成。成功驱逐: {evicted}，跳过(DS/Static): {skipped}。"
        if errors: msg += f" 失败: {len(errors)} (详情见控制台)"

        return JsonResponse({'status': True, 'msg': msg, 'details': errors})

    except Exception as e:
        return JsonResponse({'status': False, 'msg': f"排水失败: {str(e)}"})


@login_required
@csrf_exempt
def node_delete(request):
    """[AJAX] 移除节点 (缩容)"""
    if request.method != 'POST': return JsonResponse({'status': False})

    data = json.loads(request.body)
    cluster_id = data.get('cluster_id')
    node_name = data.get('node_name')

    v1, _, _, err, _ = get_k8s_client(cluster_id)
    if err: return JsonResponse({'status': False, 'msg': err})

    try:
        v1.delete_node(node_name)
        return JsonResponse({'status': True, 'msg': f"节点 {node_name} 已从集群移除 (缩容成功)"})
    except Exception as e:
        return JsonResponse({'status': False, 'msg': f"移除失败: {str(e)}"})



# ==========================================
# 新增: 节点扩容 (Add Node)
# ==========================================

@login_required
def node_candidates(request):
    """[AJAX] 获取可用于扩容的候选服务器列表 (来自 CMDB)"""
    cluster_id = request.GET.get('cluster_id')

    # 1. 获取当前集群已有的节点 IP
    v1, _, _, err, _ = get_k8s_client(cluster_id)
    existing_ips = set()
    if not err:
        try:
            nodes = v1.list_node().items
            for n in nodes:
                for addr in n.status.addresses:
                    if addr.type == "InternalIP": existing_ips.add(addr.address)
        except:
            pass

    # 2. 从 CMDB 获取所有 Running 状态的服务器
    servers = Server.objects.filter(status='Running')

    candidates = []
    for s in servers:
        # 排除已在集群中的节点
        if s.ip_address not in existing_ips:
            candidates.append({
                'id': s.id,
                'hostname': s.hostname,
                'ip': s.ip_address,
                'os': s.os_name,
                'cpu': s.cpu_cores,
                'mem': s.memory_gb
            })

    return JsonResponse({'status': True, 'candidates': candidates})




@login_required
def node_get_token(request):
    """[AJAX] 自动从 Master 节点获取 kubeadm join 命令"""
    cluster_id = request.GET.get('cluster_id')
    v1, _, _, err, _ = get_k8s_client(cluster_id)
    if err: return JsonResponse({'status': False, 'msg': err})

    try:
        # 1. 通过 K8s API 找到 Master 节点 IP
        # 兼容新老版本的 Label (control-plane 或 master)
        nodes = v1.list_node(label_selector='node-role.kubernetes.io/control-plane').items
        if not nodes:
            nodes = v1.list_node(label_selector='node-role.kubernetes.io/master').items

        if not nodes:
            return JsonResponse({'status': False, 'msg': '无法在集群中识别出 Master 节点'})

        master_ips = []
        for n in nodes:
            for addr in n.status.addresses:
                if addr.type == 'InternalIP':
                    master_ips.append(addr.address)

        # 2. 在 CMDB 中查找对应的 Master 服务器资产 (需要 SSH 权限)
        masters_in_cmdb = Server.objects.filter(ip_address__in=master_ips)

        if not masters_in_cmdb.exists():
            return JsonResponse({'status': False, 'msg': f'Master IP {master_ips} 未在 CMDB 中注册，无法 SSH 获取令牌'})

        # 3. 尝试 SSH 连接并生成令牌
        # 使用 --print-join-command 直接获取完整命令
        cmd = "sudo kubeadm token create --print-join-command"
        join_cmd = ""
        error_logs = []

        for server in masters_in_cmdb:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                pwd = str(server.password) if server.password else None
                client.connect(server.ip_address, port=server.port, username=server.username, password=pwd, timeout=5)

                stdin, stdout, stderr = client.exec_command(cmd)
                exit_status = stdout.channel.recv_exit_status()

                if exit_status == 0:
                    join_cmd = stdout.read().decode().strip()
                    client.close()
                    break  # 成功即退出
                else:
                    err_msg = stderr.read().decode().strip()
                    error_logs.append(f"{server.ip_address}: {err_msg}")
                    client.close()
            except Exception as e:
                error_logs.append(f"{server.ip_address}: {str(e)}")

        if join_cmd:
            return JsonResponse({'status': True, 'command': join_cmd})
        else:
            return JsonResponse({'status': False, 'msg': f'连接 Master 失败: {"; ".join(error_logs)}'})

    except Exception as e:
        return JsonResponse({'status': False, 'msg': str(e)})

logger = logging.getLogger(__name__)


def get_install_script_content():
    """读取同目录下的 install_k8s.sh 文件"""
    try:
        # 获取当前 views.py 文件所在的目录
        current_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(current_dir,'install_k8s.sh')

        with open(script_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error(f"读取安装脚本失败: {e}")
        return None



# ==========================================
# [新增] 任务状态查询接口
# ==========================================
@login_required
def node_task_status(request):
    """根据 task_id 查询 Celery 任务状态"""
    task_id = request.GET.get('task_id')
    if not task_id:
        return JsonResponse({'status': 'ERROR', 'msg': '缺少 task_id'})

    # [调试] 打印当前查询的 ID
    print(f"--- [Debug] Querying Task: {task_id} ---")

    # 1. 尝试使用全局 app 查询
    result = AsyncResult(task_id, app=celery_app)

    # [调试] 打印后端连接信息 (确认 Django 连的是哪个 Redis)
    backend_url = celery_app.conf.get('result_backend') or celery_app.conf.get('CELERY_RESULT_BACKEND')
    print(f"--- [Debug] Current Backend: {backend_url} ---")
    print(f"--- [Debug] Task State: {result.state} ---")

    response_data = {
        'state': result.state,
        'ready': result.ready(),
    }

    if result.ready():
        print(f"--- [Debug] Task Ready! Result: {result.result} ---")
        if result.successful():
            response_data['result'] = result.result
        else:
            response_data['result'] = str(result.result)

    return JsonResponse(response_data)


# ==========================================
# 辅助函数: 获取集群 Kubernetes 版本 (新增)
# ==========================================
def get_cluster_k8s_version(cluster_id):
    """
    通过 K8s API 获取集群控制平面的版本号。
    """
    v1, _, _, err, _ = get_k8s_client(cluster_id)
    if err or not v1: return None

    try:
        # 获取任意一个节点的版本信息，通常 Master 节点会准确
        nodes = v1.list_node().items
        if not nodes:
            return None

        # 查找 Master 节点版本 (使用 control-plane label)
        master_nodes = [n for n in nodes if
                        'node-role.kubernetes.io/control-plane' in n.metadata.labels or 'node-role.kubernetes.io/master' in n.metadata.labels]

        if master_nodes:
            # 提取版本号，例如 'v1.28.3'
            full_version = master_nodes[0].status.node_info.kubelet_version
            # 返回去掉 'v' 的版本号，例如 '1.28.3'
            return full_version.lstrip('v')

        # 如果找不到 Master 节点标签，返回第一个节点的版本
        return nodes[0].status.node_info.kubelet_version.lstrip('v')

    except Exception as e:
        logger.error(f"获取集群 {cluster_id} 版本失败: {str(e)}")
        return None


# ==========================================
# [修改] 扩容接口 (返回 task_id)
# ==========================================
@login_required
@csrf_exempt
def node_add_execute(request):
    """[AJAX] 提交节点扩容任务 (异步)"""
    if request.method != 'POST': return JsonResponse({'status': False})

    try:
        data = json.loads(request.body)
        server_ids = data.get('server_ids', [])
        join_command = data.get('join_command')
        auto_install = data.get('auto_install', False)
        cluster_id = data.get('cluster_id')  # 前端提交时必须包含 cluster_id

        if not server_ids: return JsonResponse({'status': False, 'msg': "未选择服务器"})
        if not join_command: return JsonResponse({'status': False, 'msg': "缺少 Join Command"})
        if not cluster_id: return JsonResponse({'status': False, 'msg': "缺少集群 ID"})

        k8s_version = None
        if auto_install:
            # 1. 自动安装模式下，查询 Master 版本
            k8s_version = get_cluster_k8s_version(cluster_id)
            if not k8s_version:
                return JsonResponse({'status': False, 'msg': "无法获取 Master 节点 Kubernetes 版本，无法自动安装。"})
            logger.info(f"Master Version detected: {k8s_version}")

        # 2. 调用 Celery 异步任务 (新任务签名包含 k8s_version)
        # 如果 auto_install=False, k8s_version 将是 None，任务中将安装最新版本
        task = k8s_node_add_task.delay(server_ids, join_command, auto_install, k8s_version)


        # === 修改点：返回 task_id ===
        return JsonResponse({
            'status': True,
            'task_id': task.id,  # 返回任务ID给前端
            'msg': f"已提交后台任务 (ID: {task.id})，正在执行..."
        })
    except Exception as e:
        logger.error(f"任务提交失败: {str(e)}")
        return JsonResponse({'status': False, 'msg': f"任务提交失败: {str(e)}"})


@login_required
def secret_list(request):
    ctx = get_common_context(request)
    if ctx['error']: return render(request, 'k8s/secret_list.html', ctx)

    try:
        ns = ctx['current_namespace']
        # 根据是否选择了 Namespace 获取列表
        if ns:
            items = ctx['core_v1'].list_namespaced_secret(ns).items
        else:
            items = ctx['core_v1'].list_secret_for_all_namespaces().items

        data = []
        for s in items:
            # 统计 Keys，不直接显示明文内容以保密
            keys = list(s.data.keys()) if s.data else []
            data.append({
                'name': s.metadata.name,
                'namespace': s.metadata.namespace,
                'type': s.type,  # e.g. Opaque, kubernetes.io/tls
                'keys': keys,
                'key_count': len(keys),
                'age': s.metadata.creation_timestamp
            })
        ctx['secrets'] = data
    except Exception as e:
        ctx['error'] = str(e)

    return render(request, 'k8s/secret_list.html', ctx)



# ==========================================
# 6. Secret (配置与密钥)
# ==========================================
@login_required
@csrf_exempt
def secret_create(request):
    """[AJAX] 创建 Secret"""
    if request.method != 'POST': return JsonResponse({'status': False})

    try:
        # 解析前端 JSON 数据
        req = json.loads(request.body)
        cluster_id = req.get('cluster_id')
        name = req.get('name')
        namespace = req.get('namespace')
        kv_list = req.get('data', [])  # 格式: [{'key':'k1', 'value':'v1'}, ...]

        if not all([cluster_id, name, namespace]):
            return JsonResponse({'status': False, 'msg': '参数不完整'})

        v1, _, _, err, _ = get_k8s_client(cluster_id)
        if err: return JsonResponse({'status': False, 'msg': err})

        # 构建 Secret Data (需 Base64 编码)
        secret_data = {}
        for item in kv_list:
            k = item.get('key')
            v = item.get('value')
            if k and v:
                # 编码过程: String -> Bytes -> Base64 Bytes -> String
                encoded_v = base64.b64encode(v.encode('utf-8')).decode('utf-8')
                secret_data[k] = encoded_v

        # 创建对象
        body = k8s_client.V1Secret(
            api_version="v1",
            kind="Secret",
            metadata=k8s_client.V1ObjectMeta(name=name, namespace=namespace),
            type="Opaque",  # 默认创建 Opaque 类型
            data=secret_data
        )

        v1.create_namespaced_secret(namespace, body)
        return JsonResponse({'status': True, 'msg': '创建成功'})

    except Exception as e:
        return JsonResponse({'status': False, 'msg': f"创建失败: {str(e)}"})


@login_required
@csrf_exempt
def secret_delete(request):
    """[AJAX] 删除 Secret"""
    if request.method != 'POST': return JsonResponse({'status': False})

    req = json.loads(request.body)
    cluster_id = req.get('cluster_id')
    name = req.get('name')
    namespace = req.get('namespace')

    v1, _, _, err, _ = get_k8s_client(cluster_id)
    if err: return JsonResponse({'status': False, 'msg': err})

    try:
        v1.delete_namespaced_secret(name, namespace)
        return JsonResponse({'status': True, 'msg': '删除成功'})
    except Exception as e:
        return JsonResponse({'status': False, 'msg': str(e)})


@login_required
@csrf_exempt
def secret_detail(request):
    """[AJAX] 获取 Secret 详情 (解码显示)"""
    if request.method != 'POST': return JsonResponse({'status': False})

    try:
        req = json.loads(request.body)
        cluster_id = req.get('cluster_id')
        name = req.get('name')
        namespace = req.get('namespace')

        v1, _, _, err, _ = get_k8s_client(cluster_id)
        if err: return JsonResponse({'status': False, 'msg': err})

        secret = v1.read_namespaced_secret(name, namespace)

        # 解码数据以便编辑: Base64 -> Bytes -> String
        decoded_data = []
        if secret.data:
            for k, v in secret.data.items():
                try:
                    # K8s 存的是 base64 字符串，需解码
                    val = base64.b64decode(v).decode('utf-8')
                except:
                    val = "[二进制数据或无法解码]"
                decoded_data.append({'key': k, 'value': val})

        return JsonResponse({'status': True, 'data': decoded_data})

    except Exception as e:
        return JsonResponse({'status': False, 'msg': str(e)})


@login_required
@csrf_exempt
def secret_update(request):
    """[AJAX] 更新 Secret"""
    if request.method != 'POST': return JsonResponse({'status': False})

    try:
        req = json.loads(request.body)
        cluster_id = req.get('cluster_id')
        name = req.get('name')
        namespace = req.get('namespace')
        kv_list = req.get('data', [])

        v1, _, _, err, _ = get_k8s_client(cluster_id)
        if err: return JsonResponse({'status': False, 'msg': err})

        # 重新编码数据
        secret_data = {}
        for item in kv_list:
            k = item.get('key')
            v = item.get('value')
            if k and v:
                encoded_v = base64.b64encode(v.encode('utf-8')).decode('utf-8')
                secret_data[k] = encoded_v

        # 获取现有对象以保留 metadata (如 labels/annotations)
        existing = v1.read_namespaced_secret(name, namespace)
        existing.data = secret_data  # 替换 Data 部分

        v1.replace_namespaced_secret(name, namespace, existing)
        return JsonResponse({'status': True, 'msg': '更新成功'})

    except Exception as e:
        return JsonResponse({'status': False, 'msg': str(e)})



# ==========================================
# 7. 工作负载通用详情 (Deploy, DS, STS)
# ==========================================
@login_required
def workload_detail(request):
    """
    通用详情页：支持 Deployment, DaemonSet, StatefulSet
    功能：展示 Info, Pods, YAML 编辑
    """
    ctx = get_common_context(request)
    if ctx['error']: return render(request, 'k8s/workload_detail.html', ctx)

    kind = request.GET.get('kind')  # Deployment, DaemonSet, StatefulSet
    name = request.GET.get('name')
    namespace = request.GET.get('namespace')

    if not all([kind, name, namespace]):
        ctx['error'] = "缺少必要参数 (kind, name, namespace)"
        return render(request, 'k8s/workload_detail.html', ctx)

    apps_v1 = ctx['apps_v1']
    core_v1 = ctx['core_v1']

    try:
        # 1. 根据类型获取对象
        obj = None
        if kind == 'Deployment':
            obj = apps_v1.read_namespaced_deployment(name, namespace)
        elif kind == 'DaemonSet':
            obj = apps_v1.read_namespaced_daemon_set(name, namespace)
        elif kind == 'StatefulSet':
            obj = apps_v1.read_namespaced_stateful_set(name, namespace)

        if not obj:
            raise Exception(f"未找到 {kind}: {name}")

        # 2. 生成 YAML 文本 (用于编辑器显示)
        # 使用 K8s client 自带的 sanitize 方法转为纯字典，再 dump 成 yaml
        from kubernetes import client
        api_client = client.ApiClient()
        obj_dict = api_client.sanitize_for_serialization(obj)
        # 清理一些不必要的字段 (managedFields 等) 以保持 YAML 简洁
        if 'metadata' in obj_dict and 'managedFields' in obj_dict['metadata']:
            del obj_dict['metadata']['managedFields']

        yaml_content = yaml.dump(obj_dict, default_flow_style=False)

        # 3. 获取关联 Pod (通过 Label Selector)
        selector_str = ""
        if obj.spec.selector.match_labels:
            selector_str = ",".join([f"{k}={v}" for k, v in obj.spec.selector.match_labels.items()])

        pods_data = []
        if selector_str:
            pod_list = core_v1.list_namespaced_pod(namespace, label_selector=selector_str).items
            for p in pod_list:
                pods_data.append({
                    'name': p.metadata.name,
                    'namespace': p.metadata.namespace,
                    'ip': p.status.pod_ip,
                    'node': p.spec.node_name,
                    'status': p.status.phase,
                    'restarts': sum(
                        c.restart_count for c in p.status.container_statuses) if p.status.container_statuses else 0,
                    'age': p.metadata.creation_timestamp
                })

        # 4. 组装上下文
        ctx['workload'] = {
            'kind': kind,
            'name': name,
            'namespace': namespace,
            'yaml': yaml_content,
            'replicas': obj.spec.replicas if hasattr(obj.spec, 'replicas') else '-',
            'images': [c.image for c in obj.spec.template.spec.containers],
            'created': obj.metadata.creation_timestamp
        }
        ctx['pods'] = pods_data

    except Exception as e:
        ctx['error'] = str(e)

    return render(request, 'k8s/workload_detail.html', ctx)


@login_required
@csrf_exempt
def workload_update_yaml(request):
    """[AJAX] 更新工作负载 YAML"""
    if request.method != 'POST': return JsonResponse({'status': False})
    try:
        data = json.loads(request.body)
        cluster_id = data.get('cluster_id')
        kind = data.get('kind')
        name = data.get('name')
        namespace = data.get('namespace')
        yaml_content = data.get('yaml')

        _, apps_v1, _, err, _ = get_k8s_client(cluster_id)
        if err: return JsonResponse({'status': False, 'msg': err})

        # 解析 YAML
        new_obj = yaml.safe_load(yaml_content)

        # 执行替换
        if kind == 'Deployment':
            apps_v1.replace_namespaced_deployment(name, namespace, new_obj)
        elif kind == 'DaemonSet':
            apps_v1.replace_namespaced_daemon_set(name, namespace, new_obj)
        elif kind == 'StatefulSet':
            apps_v1.replace_namespaced_stateful_set(name, namespace, new_obj)

        return JsonResponse({'status': True, 'msg': 'YAML 更新成功，集群正在应用变更...'})
    except Exception as e:
        return JsonResponse({'status': False, 'msg': f"更新失败: {str(e)}"})


@login_required
@csrf_exempt
def workload_restart(request):
    """
    [AJAX] 滚动重启 (Rollout Restart)
    原理: 修改 annotations 添加 kubectl.kubernetes.io/restartedAt 时间戳
    """
    if request.method != 'POST': return JsonResponse({'status': False})
    try:
        data = json.loads(request.body)
        cluster_id = data.get('cluster_id')
        kind = data.get('kind')
        name = data.get('name')
        namespace = data.get('namespace')

        _, apps_v1, _, err, _ = get_k8s_client(cluster_id)
        if err: return JsonResponse({'status': False, 'msg': err})

        now = datetime.datetime.utcnow().isoformat()
        body = {
            'spec': {
                'template': {
                    'metadata': {
                        'annotations': {
                            'kubectl.kubernetes.io/restartedAt': now
                        }
                    }
                }
            }
        }

        if kind == 'Deployment':
            apps_v1.patch_namespaced_deployment(name, namespace, body)
        elif kind == 'DaemonSet':
            apps_v1.patch_namespaced_daemon_set(name, namespace, body)
        elif kind == 'StatefulSet':
            apps_v1.patch_namespaced_stateful_set(name, namespace, body)

        return JsonResponse({'status': True, 'msg': f'{kind} {name} 重启指令已下发'})
    except Exception as e:
        return JsonResponse({'status': False, 'msg': str(e)})


# k8s_manager/views.py

@login_required
@csrf_exempt
def workload_describe(request):
    """
    [AJAX] 获取类似 kubectl describe 的详细信息（包含 Events）
    支持: Deployment, DaemonSet, StatefulSet, Pod, Node
    """
    if request.method != 'POST': return JsonResponse({'status': False})

    try:
        data = json.loads(request.body)
        cluster_id = data.get('cluster_id')
        kind = data.get('kind')
        name = data.get('name')
        namespace = data.get('namespace')  # Node 类型时此字段可能为空

        core_v1, apps_v1, _, err, _ = get_k8s_client(cluster_id)
        if err: return JsonResponse({'status': False, 'msg': err})

        obj = None
        events = []

        # 1. 获取对象详情 & 事件
        if kind == 'Node':
            # Node 是集群资源，无 Namespace
            obj = core_v1.read_node(name)
            # 获取 Node 相关事件 (通常涉及该 Node 的事件)
            field_selector = f"involvedObject.name={name},involvedObject.kind=Node"
            events = core_v1.list_event_for_all_namespaces(field_selector=field_selector).items

        else:
            # Namespaced 资源
            if not namespace:
                return JsonResponse({'status': False, 'msg': 'Namespace is required for this resource'})

            if kind == 'Deployment':
                obj = apps_v1.read_namespaced_deployment(name, namespace)
            elif kind == 'DaemonSet':
                obj = apps_v1.read_namespaced_daemon_set(name, namespace)
            elif kind == 'StatefulSet':
                obj = apps_v1.read_namespaced_stateful_set(name, namespace)
            elif kind == 'Pod':
                obj = core_v1.read_namespaced_pod(name, namespace)

            if obj:
                # 获取 Namespaced 事件
                field_selector = f"involvedObject.name={name},involvedObject.namespace={namespace},involvedObject.kind={kind}"
                events = core_v1.list_namespaced_event(namespace, field_selector=field_selector).items

        if not obj:
            return JsonResponse({'status': False, 'msg': f'{kind} {name} Not Found'})

        # 按时间倒序排列事件
        events.sort(key=lambda x: x.last_timestamp or x.event_time or x.metadata.creation_timestamp, reverse=True)

        # 2. 拼接文本报告
        lines = []
        meta = obj.metadata
        spec = obj.spec
        status = obj.status

        lines.append(f"Name:         {meta.name}")
        if kind != 'Node':
            lines.append(f"Namespace:    {meta.namespace}")

        # Labels & Annotations
        lines.append(f"Labels:       {json.dumps(meta.labels, indent=2) if meta.labels else '<none>'}")
        lines.append(f"Annotations:  {json.dumps(meta.annotations, indent=2) if meta.annotations else '<none>'}")
        lines.append(f"CreationTime: {meta.creation_timestamp}")

        lines.append("\n=== Status & Spec ===")

        # 通用 Conditions 展示
        if hasattr(status, 'conditions') and status.conditions:
            lines.append("Conditions:")
            for c in status.conditions:
                status_str = "True" if c.status == "True" else "False"
                lines.append(f"  Type: {c.type:<25} Status: {status_str:<10} Reason: {c.reason}")
                if c.message:
                    lines.append(f"    Message: {c.message}")

        # 针对不同类型的特有字段
        if kind == 'Node':
            lines.append(f"\nAddresses:")
            for addr in status.addresses:
                lines.append(f"  {addr.type}: {addr.address}")
            lines.append(f"\nCapacity:")
            lines.append(
                f"  CPU: {status.capacity.get('cpu')} | Memory: {status.capacity.get('memory')} | Pods: {status.capacity.get('pods')}")
            lines.append(f"Info:")
            lines.append(
                f"  OS: {status.node_info.os_image} | Kernel: {status.node_info.kernel_version} | Kubelet: {status.node_info.kubelet_version}")
            if spec.taints:
                lines.append(f"Taints: {spec.taints}")
            if spec.unschedulable:
                lines.append(f"Unschedulable: {spec.unschedulable}")

        elif kind == 'Deployment':

            lines.append(f"\nReplicas: {spec.replicas} desired | {status.updated_replicas} updated | {status.replicas} total | {status.available_replicas} available | {status.unavailable_replicas or 0} unavailable")
        elif kind == 'Pod':
            lines.append(f"\nPhase: {status.phase}")
            lines.append(f"IP: {status.pod_ip}")
            lines.append(f"Node: {spec.node_name}")
            lines.append("\nContainers:")
            for c in status.container_statuses or []:
                state_str = ""
                if c.state.running:
                    state_str = f"Running (Started: {c.state.running.started_at})"
                elif c.state.waiting:
                    state_str = f"Waiting (Reason: {c.state.waiting.reason})"
                elif c.state.terminated:
                    state_str = f"Terminated (Reason: {c.state.terminated.reason}, ExitCode: {c.state.terminated.exit_code})"

                lines.append(f"  {c.name}:")
                lines.append(f"    State: {state_str}")
                lines.append(f"    Restarts: {c.restart_count}")
                lines.append(f"    Image: {c.image}")

        lines.append("\n=== Events ===")
        if not events:
            lines.append("<No Events found>")
        else:
            lines.append(f"{'Type':<10} {'Reason':<20} {'Age':<20} {'Message'}")
            lines.append("-" * 100)
            for e in events:
                event_time = e.last_timestamp or e.event_time or e.metadata.creation_timestamp
                time_str = event_time.strftime("%Y-%m-%d %H:%M:%S") if event_time else "Unknown"
                lines.append(f"{e.type:<10} {e.reason:<20} {time_str:<20} {e.message}")

        return JsonResponse({'status': True, 'describe': "\n".join(lines)})

    except Exception as e:
        return JsonResponse({'status': False, 'msg': str(e)})


# ==========================================
# 8. Helm 应用商店 (Helm Chart Manager)
# ==========================================

def _run_helm(cluster_id, args):
    """
    Helm 命令执行封装
    :param cluster_id: 集群ID (用于获取 Kubeconfig)
    :param args: 命令参数列表 (如 ['list', '-A'])
    """
    if not shutil.which('helm'):
        return False, "服务器未安装 Helm 客户端 (Please install helm first)"

    # 获取集群配置
    try:
        cluster = K8sCluster.objects.get(id=cluster_id)
    except K8sCluster.DoesNotExist:
        return False, "Cluster not found"

    # 创建临时 Kubeconfig 文件
    # 注意：Helm 需要文件路径作为 --kubeconfig 参数
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml') as tmp:
        tmp.write(cluster.kubeconfig)
        tmp_path = tmp.name

    try:
        # 构造完整命令: helm --kubeconfig /tmp/xxx [args...]
        cmd = ['helm', '--kubeconfig', tmp_path] + args

        # 针对 repo 命令，不需要 kubeconfig (它是本地配置)，但加上也无妨
        # 执行命令
        res = subprocess.run(cmd, capture_output=True, text=True)

        if res.returncode != 0:
            return False, res.stderr
        return True, res.stdout
    except Exception as e:
        return False, str(e)
    finally:
        # 清理临时文件
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@login_required
def helm_store_index(request):
    """Helm 商店主页"""
    ctx = get_common_context(request)
    if ctx['error']: return render(request, 'k8s/helm_store.html', ctx)
    return render(request, 'k8s/helm_store.html', ctx)


@login_required
@csrf_exempt
def helm_repo_api(request):
    # === 修复 1: 检查 Helm 是否存在 ===
    if not shutil.which('helm'):
        return JsonResponse({'status': False, 'msg': '服务器未安装 Helm，请联系管理员安装 (WinError 2)'})

    if request.method == 'GET':
        try:
            # 增加 shell=True 在 Windows 下有时能解决路径问题，但在 Linux 不建议
            # 这里保持 subprocess.run，依靠 shutil.which 做前置检查
            res = subprocess.run(['helm', 'repo', 'list', '-o', 'json'], capture_output=True, text=True)
            if res.returncode != 0:
                return JsonResponse({'status': True, 'data': []})
            return JsonResponse({'status': True, 'data': json.loads(res.stdout)})
        except Exception as e:
            return JsonResponse({'status': False, 'msg': f"执行出错: {str(e)}"})

    elif request.method == 'POST':
        action = request.POST.get('action')
        name = request.POST.get('name')
        url = request.POST.get('url')

        try:
            if action == 'add':
                if not name or not url: return JsonResponse({'status': False, 'msg': '缺少参数'})
                res = subprocess.run(['helm', 'repo', 'add', name, url], capture_output=True, text=True)
                if res.returncode == 0:
                    subprocess.run(['helm', 'repo', 'update'], capture_output=True)
                    return JsonResponse({'status': True, 'msg': '仓库添加成功'})
                return JsonResponse({'status': False, 'msg': res.stderr})

            elif action == 'delete':
                res = subprocess.run(['helm', 'repo', 'remove', name], capture_output=True, text=True)
                return JsonResponse(
                    {'status': res.returncode == 0, 'msg': res.stderr if res.returncode != 0 else '删除成功'})
        except Exception as e:
            return JsonResponse({'status': False, 'msg': str(e)})

    return JsonResponse({'status': False})


@login_required
@csrf_exempt
def helm_chart_api(request):
    # === 修复 2: 检查 Helm 是否存在 ===
    if not shutil.which('helm'):
        return JsonResponse({'status': False, 'msg': '服务器未安装 Helm'})

    action = request.GET.get('action')

    try:
        if action == 'search':
            keyword = request.GET.get('keyword', '')
            cmd = ['helm', 'search', 'repo', keyword, '-o', 'json']
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                return JsonResponse({'status': True, 'data': json.loads(res.stdout)})
            return JsonResponse({'status': False, 'msg': res.stderr})

        elif action == 'values':
            chart = request.GET.get('chart')
            res = subprocess.run(['helm', 'show', 'values', chart], capture_output=True, text=True)
            if res.returncode == 0:
                return JsonResponse({'status': True, 'values': res.stdout})
            return JsonResponse({'status': False, 'msg': res.stderr})

    except Exception as e:
        return JsonResponse({'status': False, 'msg': str(e)})

    return JsonResponse({'status': False})


@login_required
@csrf_exempt
def helm_release_api(request):
    """[AJAX] 发布管理: List / Install / Uninstall"""
    cluster_id = request.POST.get('cluster_id') or request.GET.get('cluster_id')
    if not cluster_id: return JsonResponse({'status': False, 'msg': 'Cluster ID Required'})

    if request.method == 'GET':
        # helm list -A -o json
        success, out = _run_helm(cluster_id, ['list', '-A', '-o', 'json'])
        if success:
            return JsonResponse({'status': True, 'data': json.loads(out)})
        return JsonResponse({'status': False, 'msg': out})

    elif request.method == 'POST':
        action = request.POST.get('action')

        if action == 'install':
            release_name = request.POST.get('name')
            chart = request.POST.get('chart')
            namespace = request.POST.get('namespace', 'default')
            values_yaml = request.POST.get('values', '')

            # 将 values 写入临时文件
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml') as f:
                f.write(values_yaml)
                val_path = f.name

            try:
                # helm install name chart -n ns -f values.yaml --create-namespace
                cmd = ['install', release_name, chart, '-n', namespace, '-f', val_path, '--create-namespace']
                success, out = _run_helm(cluster_id, cmd)
                if success:
                    return JsonResponse({'status': True, 'msg': f'部署成功: {out}'})
                return JsonResponse({'status': False, 'msg': out})
            finally:
                os.remove(val_path)

        elif action == 'uninstall':
            name = request.POST.get('name')
            ns = request.POST.get('namespace')
            cmd = ['uninstall', name, '-n', ns]
            success, out = _run_helm(cluster_id, cmd)
            return JsonResponse({'status': success, 'msg': out})

    return JsonResponse({'status': False})


# ==========================================
# 9. 存储管理 (Storage)
# ==========================================

@login_required
def pvc_list(request):
    """PVC 列表 (Namespace 级别)"""
    ctx = get_common_context(request)
    if ctx['error']: return render(request, 'k8s/pvc_list.html', ctx)

    core_v1 = ctx['core_v1']
    namespace = ctx['current_namespace']

    try:
        # 1. 获取 PVC
        if namespace:
            pvcs = core_v1.list_namespaced_persistent_volume_claim(namespace).items
        else:
            pvcs = core_v1.list_persistent_volume_claim_for_all_namespaces().items

        # 2. 获取 Pods 以建立 "PVC -> Pod" 的反向关联
        # (即：谁在使用这个 PVC？)
        pvc_pod_map = {}
        if namespace:
            pods = core_v1.list_namespaced_pod(namespace).items
        else:
            pods = core_v1.list_pod_for_all_namespaces().items

        for p in pods:
            if not p.spec.volumes: continue
            for vol in p.spec.volumes:
                if vol.persistent_volume_claim:
                    claim_name = vol.persistent_volume_claim.claim_name
                    # 如果是全命名空间视图，key 需要包含 namespace
                    key = claim_name if namespace else f"{p.metadata.namespace}/{claim_name}"

                    if key not in pvc_pod_map: pvc_pod_map[key] = []
                    pvc_pod_map[key].append(p.metadata.name)

        data = []
        for item in pvcs:
            key = item.metadata.name if namespace else f"{item.metadata.namespace}/{item.metadata.name}"

            data.append({
                'name': item.metadata.name,
                'namespace': item.metadata.namespace,
                'status': item.status.phase,
                'capacity': item.status.capacity.get('storage') if item.status.capacity else '-',
                'access_modes': item.spec.access_modes,
                'storage_class': item.spec.storage_class_name,
                'volume': item.spec.volume_name,  # 绑定的 PV 名
                'age': item.metadata.creation_timestamp,
                'mounted_by': pvc_pod_map.get(key, [])  # 使用该 PVC 的 Pod 列表
            })

        ctx['pvcs'] = data

    except Exception as e:
        ctx['error'] = str(e)

    return render(request, 'k8s/pvc_list.html', ctx)


@login_required
def pv_list(request):
    """PV 列表 (Cluster 级别)"""
    ctx = get_common_context(request)
    if ctx['error']: return render(request, 'k8s/pv_list.html', ctx)

    try:
        pvs = ctx['core_v1'].list_persistent_volume().items
        data = []
        for item in pvs:
            # 1. 获取绑定的 PVC
            claim_info = "-"
            if item.spec.claim_ref:
                claim_info = f"{item.spec.claim_ref.namespace}/{item.spec.claim_ref.name}"

            # 2. 解析底层存储来源 (NFS/HostPath/CSI/RBD...)
            source_type = "Unknown"
            source_detail = ""

            if item.spec.nfs:
                source_type = "NFS"
                source_detail = f"{item.spec.nfs.server}:{item.spec.nfs.path}"
            elif item.spec.host_path:
                source_type = "HostPath"
                source_detail = item.spec.host_path.path
            elif item.spec.csi:
                source_type = "CSI"
                source_detail = f"{item.spec.csi.driver} ({item.spec.csi.volume_handle})"
            elif item.spec.local:
                source_type = "Local"
                source_detail = item.spec.local.path

            data.append({
                'name': item.metadata.name,
                'status': item.status.phase,
                'capacity': item.spec.capacity.get('storage') if item.spec.capacity else '-',
                'access_modes': item.spec.access_modes,
                'reclaim_policy': item.spec.persistent_volume_reclaim_policy,
                'storage_class': item.spec.storage_class_name,
                'claim': claim_info,
                'source_type': source_type,
                'source_detail': source_detail,
                'age': item.metadata.creation_timestamp
            })
        ctx['pvs'] = data
    except Exception as e:
        ctx['error'] = str(e)

    return render(request, 'k8s/pv_list.html', ctx)


@login_required
def storage_class_list(request):
    """StorageClass 列表"""
    ctx = get_common_context(request)
    if ctx['error']: return render(request, 'k8s/storageclass_list.html', ctx)

    try:
        # StorageClass 属于 storage.k8s.io API 组
        storage_v1 = client.StorageV1Api(ctx['core_v1'].api_client)
        scs = storage_v1.list_storage_class().items

        data = []
        for item in scs:
            data.append({
                'name': item.metadata.name,
                'provisioner': item.provisioner,
                'reclaim_policy': item.reclaim_policy,
                'binding_mode': item.volume_binding_mode,
                'age': item.metadata.creation_timestamp
            })
        ctx['scs'] = data
    except Exception as e:
        ctx['error'] = str(e)

    return render(request, 'k8s/storageclass_list.html', ctx)


# ==========================================
# 存储资源操作 (CRUD)
# ==========================================

@login_required
@csrf_exempt
def pvc_create(request):
    """[AJAX] PVC 快速创建 (表单)"""
    if request.method != 'POST': return JsonResponse({'status': False})

    try:
        data = json.loads(request.body)
        cluster_id = data.get('cluster_id')
        ns = data.get('namespace')
        name = data.get('name')
        sc = data.get('storage_class')
        size = data.get('size')  # e.g. "10Gi"
        mode = data.get('access_mode')  # e.g. "ReadWriteOnce"

        core_v1, _, _, err, _ = get_k8s_client(cluster_id)
        if err: return JsonResponse({'status': False, 'msg': err})

        # 构造 PVC 对象
        body = client.V1PersistentVolumeClaim(
            api_version="v1",
            kind="PersistentVolumeClaim",
            metadata=client.V1ObjectMeta(name=name, namespace=ns),
            spec=client.V1PersistentVolumeClaimSpec(
                access_modes=[mode],
                resources=client.V1ResourceRequirements(
                    requests={"storage": size}
                ),
                storage_class_name=sc if sc else None
            )
        )

        core_v1.create_namespaced_persistent_volume_claim(ns, body)
        return JsonResponse({'status': True, 'msg': 'PVC 创建成功'})

    except Exception as e:
        return JsonResponse({'status': False, 'msg': str(e)})


@login_required
@csrf_exempt
def storage_resource_api(request):
    """
    [AJAX] 存储资源通用操作: GetYAML / Update / Delete
    支持: PersistentVolume (pv), PersistentVolumeClaim (pvc), StorageClass (sc)
    """
    cluster_id = request.GET.get('cluster_id') or request.POST.get('cluster_id')
    kind = request.GET.get('kind') or request.POST.get('kind')  # pv, pvc, sc
    name = request.GET.get('name') or request.POST.get('name')
    namespace = request.GET.get('namespace') or request.POST.get('namespace')
    action = request.GET.get('action') or request.POST.get('action')  # get_yaml, update, delete

    if not all([cluster_id, kind, name, action]):
        return JsonResponse({'status': False, 'msg': '参数缺失'})

    core_v1, _, _, err, _ = get_k8s_client(cluster_id)
    if err: return JsonResponse({'status': False, 'msg': err})

    # StorageClass 需要单独的 API Client
    storage_v1 = client.StorageV1Api(core_v1.api_client)

    try:
        # --- 1. Get YAML ---
        if action == 'get_yaml':
            obj = None
            if kind == 'pvc':
                obj = core_v1.read_namespaced_persistent_volume_claim(name, namespace)
            elif kind == 'pv':
                obj = core_v1.read_persistent_volume(name)
            elif kind == 'sc':
                obj = storage_v1.read_storage_class(name)

            if not obj: return JsonResponse({'status': False, 'msg': 'Not Found'})

            # 序列化为 YAML
            _client = client.ApiClient()
            obj_dict = _client.sanitize_for_serialization(obj)
            # 清理只读字段
            if 'metadata' in obj_dict and 'managedFields' in obj_dict['metadata']:
                del obj_dict['metadata']['managedFields']

            yaml_str = yaml.dump(obj_dict, default_flow_style=False)
            return JsonResponse({'status': True, 'yaml': yaml_str})

        # --- 2. Delete ---
        elif action == 'delete':
            if kind == 'pvc':
                core_v1.delete_namespaced_persistent_volume_claim(name, namespace)
            elif kind == 'pv':
                core_v1.delete_persistent_volume(name)
            elif kind == 'sc':
                storage_v1.delete_storage_class(name)
            return JsonResponse({'status': True, 'msg': '删除指令已下发'})

        # --- 3. Update (Apply YAML) ---
        elif action == 'update':
            yaml_content = request.POST.get('yaml')
            if not yaml_content: return JsonResponse({'status': False, 'msg': 'YAML为空'})

            new_obj = yaml.safe_load(yaml_content)

            if kind == 'pvc':
                core_v1.replace_namespaced_persistent_volume_claim(name, namespace, new_obj)
            elif kind == 'pv':
                core_v1.replace_persistent_volume(name, new_obj)
            elif kind == 'sc':
                # StorageClass 通常不支持 replace (immutable)，建议提示用户删除重建
                # 这里尝试 patch
                storage_v1.patch_storage_class(name, new_obj)

            return JsonResponse({'status': True, 'msg': '更新成功'})

    except Exception as e:
        return JsonResponse({'status': False, 'msg': str(e)})

    return JsonResponse({'status': False, 'msg': 'Unknown Action'})


# ==========================================
# 11. ConfigMap 配置管理
# ==========================================

@login_required
def configmap_list(request):
    """ConfigMap 列表"""
    ctx = get_common_context(request)
    if ctx['error']: return render(request, 'k8s/configmap_list.html', ctx)

    try:
        if ctx['current_namespace']:
            cms = ctx['core_v1'].list_namespaced_config_map(ctx['current_namespace']).items
        else:
            cms = ctx['core_v1'].list_config_map_for_all_namespaces().items

        data = []
        for cm in cms:
            # 简单统计 Keys 数量
            keys = list(cm.data.keys()) if cm.data else []
            data.append({
                'name': cm.metadata.name,
                'namespace': cm.metadata.namespace,
                'keys_count': len(keys),
                'keys_str': ', '.join(keys[:3]) + ('...' if len(keys) > 3 else ''),
                'age': cm.metadata.creation_timestamp
            })
        ctx['cms'] = data
    except Exception as e:
        ctx['error'] = str(e)

    return render(request, 'k8s/configmap_list.html', ctx)


@login_required
@csrf_exempt
def configmap_api(request):
    """[AJAX] ConfigMap 增删改查 + 历史 + 热更新"""
    setup_custom_yaml()
    if request.method == 'POST':
        action = request.POST.get('action')
        cluster_id = request.POST.get('cluster_id')
        ns = request.POST.get('namespace')
        name = request.POST.get('name')

        core_v1, apps_v1, _, err, _ = get_k8s_client(cluster_id)
        if err: return JsonResponse({'status': False, 'msg': err})

        # --- 1. 获取详情 / 历史 ---
        if action == 'get':
            try:
                cm = core_v1.read_namespaced_config_map(name, ns)
                # 转为 YAML 供编辑器使用
                raw_data = cm.data if cm.data else {}
                import  yaml
                yaml_data = yaml.dump(
                    raw_data,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False  # 保持 Key 的顺序
                )
                return JsonResponse({'status': True, 'data': yaml_data})
            except Exception as e:
                return JsonResponse({'status': False, 'msg': str(e)})

        # --- 2. 保存更新 (含版本控制 & 热更新) ---
        elif action == 'update':
            content = request.POST.get('content')
            auto_restart = request.POST.get('auto_restart') == 'true'
            remarks = request.POST.get('remarks', 'Update via Web Console')

            try:
                import yaml
                new_data = yaml.safe_load(content)  # 解析 YAML

                # A. 获取旧版本并保存历史
                try:
                    old_cm = core_v1.read_namespaced_config_map(name, ns)
                    old_yaml = yaml.dump(old_cm.data if old_cm.data else {}, default_flow_style=False, allow_unicode=True)

                    # 计算新版本号
                    last_ver = ConfigMapHistory.objects.filter(cluster_id=cluster_id, namespace=ns, name=name).first()
                    new_ver = (last_ver.version + 1) if last_ver else 1

                    # 存入数据库
                    ConfigMapHistory.objects.create(
                        cluster_id=cluster_id, namespace=ns, name=name,
                        data=old_yaml, version=new_ver,
                        user=request.user.username, description=remarks
                    )
                except Exception as e:
                    print(f"Warning: Failed to save history: {e}")

                # B. 更新 K8s ConfigMap
                old_cm.data = new_data
                core_v1.replace_namespaced_config_map(name, ns, old_cm)

                msg = "配置已更新"

                # C. 热更新 (滚动重启关联 Deployment)
                if auto_restart:
                    restarted = _trigger_rolling_update(apps_v1, ns, name)
                    if restarted:
                        msg += f"，并触发了 {len(restarted)} 个应用的滚动更新"
                    else:
                        msg += "，但未发现直接引用该配置的 Deployment"

                return JsonResponse({'status': True, 'msg': msg})
            except Exception as e:
                return JsonResponse({'status': False, 'msg': str(e)})

        # --- 3. 获取历史列表 ---
        elif action == 'history_list':
            hists = ConfigMapHistory.objects.filter(
                cluster_id=cluster_id, namespace=ns, name=name
            ).values('id', 'version', 'created_at', 'user', 'description')[:10]  # 取最近10条
            return JsonResponse({'status': True, 'data': list(hists)})

        # --- 4. 获取特定历史版本内容 (用于 Diff) ---
        elif action == 'get_history_content':
            hid = request.POST.get('history_id')
            hist = ConfigMapHistory.objects.get(id=hid)
            return JsonResponse({'status': True, 'data': hist.data})

    return JsonResponse({'status': False})


def _trigger_rolling_update(apps_v1, namespace, cm_name):
    """
    查找并重启引用了指定 ConfigMap 的 Deployments
    """
    restarted_apps = []
    deps = apps_v1.list_namespaced_deployment(namespace).items

    for d in deps:
        is_used = False
        containers = d.spec.template.spec.containers
        volumes = d.spec.template.spec.volumes

        # 1. 检查 envFrom (configMapRef)
        for c in containers:
            if c.env_from:
                for env in c.env_from:
                    if env.config_map_ref and env.config_map_ref.name == cm_name:
                        is_used = True;
                        break
            if is_used: break

        # 2. 检查 volumes (configMap)
        if not is_used and volumes:
            for v in volumes:
                if v.config_map and v.config_map.name == cm_name:
                    is_used = True;
                    break

        # 3. 执行重启 (Patch Annotation)
        if is_used:
            body = {
                'spec': {
                    'template': {
                        'metadata': {
                            'annotations': {
                                'kubectl.kubernetes.io/restartedAt': datetime.datetime.utcnow().isoformat()
                            }
                        }
                    }
                }
            }
            apps_v1.patch_namespaced_deployment(d.metadata.name, namespace, body)
            restarted_apps.append(d.metadata.name)

    return restarted_apps


# ==========================================
# 12. 镜像管理 (ImageOps)
# ==========================================

@login_required
@csrf_exempt
def node_image_ops(request):
    """[AJAX] 节点镜像操作：清理 / 预热"""
    if request.method != 'POST': return JsonResponse({'status': False})

    action = request.POST.get('action')
    cluster_id = request.POST.get('cluster_id')

    core_v1, apps_v1, _, err, _ = get_k8s_client(cluster_id)
    if err: return JsonResponse({'status': False, 'msg': err})

    # --- 1. 单节点清理悬空镜像 (SSH) ---
    if action == 'clean':
        node_name = request.POST.get('node_name')
        try:
            # A. 获取节点 IP (InternalIP)
            node = core_v1.read_node(node_name)
            node_ip = None
            for addr in node.status.addresses:
                if addr.type == 'InternalIP':
                    node_ip = addr.address
                    break

            if not node_ip:
                return JsonResponse({'status': False, 'msg': '无法获取节点 InternalIP'})

            # B. 匹配 CMDB Server 资产
            server = Server.objects.filter(ip_address=node_ip).first()
            if not server:
                return JsonResponse({'status': False,
                                     'msg': f'CMDB 中未找到 IP 为 {node_ip} 的服务器，无法建立 SSH 连接执行清理。请先在资产管理中录入该节点。'})

            # C. SSH 执行清理命令 (兼容 containerd 和 docker)
            client = get_secure_ssh_client(server, timeout=10)

            # 命令解释：
            # 1. 尝试 crictl (k8s 推荐): crictl rmi --prune
            # 2. 失败则尝试 docker: docker image prune -f
            cmd = "crictl rmi --prune 2>/dev/null || docker image prune -f"

            stdin, stdout, stderr = client.exec_command(cmd)
            exit_code = stdout.channel.recv_exit_status()
            out = stdout.read().decode().strip()
            err_msg = stderr.read().decode().strip()
            client.close()

            if exit_code == 0 or "Deleted" in out or "Total reclaimed" in out:
                return JsonResponse({'status': True, 'msg': f"清理成功:\n{out}"})
            else:
                return JsonResponse({'status': False, 'msg': f"清理可能失败 (Code {exit_code}):\n{err_msg}\n{out}"})

        except Exception as e:
            return JsonResponse({'status': False, 'msg': f"执行异常: {str(e)}"})

    # --- 2. 镜像预热 (DaemonSet) ---
    elif action == 'prewarm':
        image = request.POST.get('image')
        if not image: return JsonResponse({'status': False, 'msg': '请输入镜像地址'})

        try:
            # 创建一个 DaemonSet，拉取镜像后休眠
            # 使用时间戳防止命名冲突
            import time
            from kubernetes import client
            name = f"prewarm-{int(time.time())}"

            ds_body = client.V1DaemonSet(
                api_version="apps/v1",
                kind="DaemonSet",
                metadata=client.V1ObjectMeta(
                    name=name,
                    namespace='default',
                    labels={'app': name, 'role': 'image-prewarm'}
                ),
                spec=client.V1DaemonSetSpec(
                    selector=client.V1LabelSelector(match_labels={'app': name}),
                    template=client.V1PodTemplateSpec(
                        metadata=client.V1ObjectMeta(labels={'app': name}),
                        spec=client.V1PodSpec(
                            containers=[client.V1Container(
                                name='prewarm',
                                image=image,
                                # 拉取成功后如果不运行任何东西会 CrashLoopBackOff，所以 echo 一句然后 sleep
                                command=["/bin/sh", "-c", "echo 'Image Pulled Successfully'; sleep 3600"],
                                resources=client.V1ResourceRequirements(limits={'cpu': '10m', 'memory': '20Mi'})
                            )],
                            # 关键：容忍所有污点，确保 Master 节点也能预热
                            tolerations=[client.V1Toleration(operator="Exists")]
                        )
                    )
                )
            )

            apps_v1.create_namespaced_daemon_set('default', ds_body)

            return JsonResponse({
                'status': True,
                'msg': f'预热任务 [{name}] 已下发！\n\nK8s 正在所有节点拉取镜像 [{image}]。\n请稍后在 DaemonSet 列表中查看进度，确认全部 Ready 后请手动删除该任务。'
            })

        except Exception as e:
            return JsonResponse({'status': False, 'msg': str(e)})

    return JsonResponse({'status': False, 'msg': 'Unknown Action'})