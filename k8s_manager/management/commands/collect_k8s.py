# k8s_manager/management/commands/collect_k8s.py

import logging
import requests
from concurrent.futures import ThreadPoolExecutor
from django.core.management.base import BaseCommand
from apscheduler.schedulers.blocking import BlockingScheduler
from django.utils import timezone
from django.db import connections

# 引入模型和工具
from k8s_manager.models import K8sCluster, NodeSnapshot
from k8s_manager.utils import get_k8s_client

logger = logging.getLogger(__name__)


def collect_single_node(cluster_token, node_ip, node_name):
    """采集单个 K8s 节点数据"""
    # 每次线程操作前清理连接，防止 MySQL Gone Away
    connections.close_all()

    agent_url = f"http://{node_ip}:10055/metrics"
    try:
        # 拉取数据 (超时设为 3s 以上，因为 Agent 内部 sleep 1s)
        resp = requests.get(agent_url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()

            # 入库
            NodeSnapshot.objects.update_or_create(
                cluster_token=cluster_token,
                node_name=node_name,  # 优先使用 K8s API 中的名字，或 Agent 返回的名字
                defaults={
                    'node_ip': node_ip,
                    'kubelet_log': data.get('kubelet_log', ''),
                    'proxy_log': data.get('proxy_log', ''),
                    'runtime_status': data.get('runtime_status', ''),

                    'cpu_usage': data.get('cpu', 0),
                    'mem_usage': data.get('mem', 0),
                    'disk_usage': data.get('disk', 0),

                    'net_in': data.get('net_in', 0),
                    'net_out': data.get('net_out', 0),
                    'disk_read_rate': data.get('disk_read_rate', 0),
                    'disk_write_rate': data.get('disk_write_rate', 0),
                    'updated_at': timezone.now()
                }
            )
            # print(f"✅ {node_name} collected.")
    except Exception as e:
        logger.error(f"❌ Failed to pull {node_name} ({node_ip}): {e}")


def collect_cluster(cluster):
    """处理单个集群"""
    # 获取 K8s Client
    v1, _, _, err, _ = get_k8s_client(cluster.id)
    if err or not v1:
        logger.error(f"Skip cluster {cluster.name}: {err}")
        return

    try:
        nodes = v1.list_node().items
        tasks = []

        # 提取节点 IP 和 Name
        for n in nodes:
            node_name = n.metadata.name
            node_ip = None
            # 优先取 InternalIP
            for addr in n.status.addresses:
                if addr.type == 'InternalIP':
                    node_ip = addr.address
                    break
            # 如果没有 InternalIP，尝试 ExternalIP 或 Hostname
            if not node_ip:
                for addr in n.status.addresses:
                    if addr.type == 'ExternalIP':
                        node_ip = addr.address
                        break

            if node_ip:
                tasks.append((cluster.token, node_ip, node_name))

        # 并发采集该集群的所有节点
        if tasks:
            with ThreadPoolExecutor(max_workers=20) as executor:
                for t in tasks:
                    executor.submit(collect_single_node, *t)

    except Exception as e:
        logger.error(f"Error listing nodes for {cluster.name}: {e}")


def job_collect_all():
    """主任务：遍历所有集群"""
    logger.info("--- Start K8s Collection ---")
    clusters = K8sCluster.objects.all()
    for c in clusters:
        collect_cluster(c)


class Command(BaseCommand):
    help = "启动 K8s 拉取式监控"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('K8s Pull Monitor Started...'))

        scheduler = BlockingScheduler(timezone=timezone.get_current_timezone())
        # 每 60 秒执行一次
        scheduler.add_job(job_collect_all, 'interval', seconds=60)

        try:
            job_collect_all()  # 启动时先跑一次
            scheduler.start()
        except KeyboardInterrupt:
            self.stdout.write("Stopped.")