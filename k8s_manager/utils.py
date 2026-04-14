import yaml
import logging
from kubernetes import client, config
from .models import K8sCluster
from functools import lru_cache
import hashlib

logger = logging.getLogger(__name__)
@lru_cache(maxsize=32)
def _get_cached_api_client(kubeconfig_hash, kubeconfig_str):
    """
    内部缓存函数：根据 kubeconfig 内容返回复用的 ApiClient。
    注意：这里多传一个 hash 是为了让 lru_cache 快速比对，
    虽然 Python 字符串本身可 hash，但显式控制更稳健。
    """
    try:
        # 加载配置
        config_dict = yaml.safe_load(kubeconfig_str)
        loader = config.kube_config.KubeConfigLoader(config_dict)

        # 创建配置对象
        c = client.Configuration()
        loader.load_and_set(c)

        # 关键优化：设置连接池并发数（默认是 1，并发高时不够用）
        c.pool_maxsize = 10

        # 初始化 ApiClient (这是最耗时的步骤)
        api_client = client.ApiClient(c)
        return api_client
    except Exception as e:
        logger.error(f"初始化 K8s Client 失败: {e}")
        return None


def get_k8s_client(cluster_id=None):
    """
    获取 K8s 客户端 (CoreV1Api, AppsV1Api, NetworkingV1Api, error_msg, cluster_obj)
    """
    cluster = None
    try:
        if cluster_id:
            cluster = K8sCluster.objects.filter(id=cluster_id).first()
        else:
            # 默认取第一个
            cluster = K8sCluster.objects.first()

        if not cluster:
            return None, None, None, "未找到指定的 K8s 集群配置", None

        # 计算 hash 用于缓存 Key (如果 kubeconfig 不变，hash 就不变)
        # 使用 MD5 摘要作为 key 避免长字符串对比开销
        config_hash = hashlib.md5(cluster.kubeconfig.encode('utf-8')).hexdigest()

        # 获取缓存的 ApiClient
        api_client = _get_cached_api_client(config_hash, cluster.kubeconfig)

        if not api_client:
            return None, None, None, "K8s配置解析失败，请检查 KubeConfig 格式", cluster

        # 基于同一个 api_client 实例化不同的 API 组
        # 这些对象初始化非常快，不需要缓存
        core_v1 = client.CoreV1Api(api_client)
        apps_v1 = client.AppsV1Api(api_client)
        net_v1 = client.NetworkingV1Api(api_client)

        return core_v1, apps_v1, net_v1, None, cluster

    except Exception as e:
        logger.error(f"获取 K8s Client 异常: {e}")
        return None, None, None, f"系统异常: {str(e)}", cluster


def get_pod_events(core_v1, pod_name, namespace):
    """
    获取与该 Pod 相关的 K8s 事件 (用于分析启动失败/调度问题)
    """
    try:
        # field_selector 过滤只属于该 Pod 的事件
        events = core_v1.list_namespaced_event(
            namespace,
            field_selector=f"involvedObject.name={pod_name},involvedObject.kind=Pod"
        )
        event_msgs = []
        for e in events.items:
            # 格式：[Type] Reason: Message
            event_msgs.append(f"[{e.type}] {e.reason}: {e.message}")

        return "\n".join(event_msgs) if event_msgs else "无异常事件"
    except Exception as e:
        return f"获取事件失败: {str(e)}"


def get_node_events(core_v1, node_name):
    """
    获取与该 Node 相关的 K8s 事件 (用于分析节点故障)
    """
    try:
        # field_selector 过滤只属于该 Node 的事件
        events = core_v1.list_event_for_all_namespaces(
            field_selector=f"involvedObject.name={node_name},involvedObject.kind=Node"
        )
        event_msgs = []
        for e in events.items:
            # 格式：[Type] Reason: Message
            event_msgs.append(f"[{e.type}] {e.reason}: {e.message}")

        return "\n".join(event_msgs) if event_msgs else "无异常事件"
    except Exception as e:
        return f"获取节点事件失败: {str(e)}"


def get_java_thread_dump(core_v1, pod_name, namespace):
    """
    尝试进入 Pod 执行 jstack (用于 Java 死锁/卡顿分析)
    """
    try:
        # 优先尝试 jstack，如果 PID 1 不是 Java，尝试 kill -3 打印堆栈到 stdout
        exec_command = [
            '/bin/shell',
            '-c',
            'jstack 1 || kill -3 1'
        ]

        resp = stream.stream(core_v1.connect_get_namespaced_pod_exec,
                             pod_name,
                             namespace,
                             command=exec_command,
                             stderr=True, stdin=False,
                             stdout=True, tty=False)
        return resp
    except Exception as e:
        return f"无法获取堆栈 (非Java应用或容器缺JDK/权限不足): {str(e)}"