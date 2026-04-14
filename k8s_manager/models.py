from django.db import models
from fernet_fields import EncryptedTextField
import uuid
from cmdb.models import ServerGroup

class K8sCluster(models.Model):
    """K8s 集群配置"""
    name = models.CharField("集群名称", max_length=50, unique=True)
    kubeconfig = EncryptedTextField("KubeConfig")
    version = models.CharField("版本", max_length=20, blank=True)
    group = models.ForeignKey(ServerGroup, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="所属分组")
    # 用于 Agent 认证的 Token (自动生成)
    token = models.CharField("Agent Token", max_length=64, blank=True, unique=True)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = uuid.uuid4().hex
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class NodeSnapshot(models.Model):
    """
    节点健康快照 (由 Agent 主动上报)
    解决内网节点无法 SSH 的问题，缓存底层日志供 AI 分析
    """
    cluster_token = models.CharField(max_length=64, db_index=True)
    node_name = models.CharField(max_length=100)
    node_ip = models.CharField(max_length=50)

    # 关键组件日志 (Agent 抓取的 journalctl)
    kubelet_log = models.TextField("Kubelet日志", blank=True)
    proxy_log = models.TextField("Proxy日志", blank=True)
    runtime_status = models.TextField("运行时状态", blank=True)  # docker/containerd status

    # 基础监控
    cpu_usage = models.FloatField(default=0)
    mem_usage = models.FloatField(default=0)
    disk_usage = models.FloatField(default=0)
    net_in = models.FloatField("入站流量(KB/s)", default=0.0)
    net_out = models.FloatField("出站流量(KB/s)", default=0.0)
    disk_read_rate = models.FloatField("磁盘读取(KB/s)", default=0.0)
    disk_write_rate = models.FloatField("磁盘写入(KB/s)", default=0.0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('cluster_token', 'node_name')


class ConfigMapHistory(models.Model):
    """ConfigMap 历史版本控制"""
    cluster_id = models.IntegerField("集群ID")
    namespace = models.CharField("命名空间", max_length=100)
    name = models.CharField("名称", max_length=200)

    # 存储 YAML/JSON 格式的内容
    data = models.TextField("配置内容")

    # 变更记录
    version = models.IntegerField("版本号")
    user = models.CharField("操作人", max_length=100, default="system")
    created_at = models.DateTimeField("修改时间", auto_now_add=True)
    description = models.CharField("变更备注", max_length=255, blank=True)

    class Meta:
        ordering = ['-version']
        verbose_name = "配置历史"

