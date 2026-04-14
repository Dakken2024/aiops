#!/bin/bash
# K8s Agent (Worker Node) 国内优化安装脚本 - 包含EPEL源修复
# 只使用国内镜像源，不连接任何国外官方源
# 使用方法:
#   sudo K8S_VERSION=<Master版本> JOIN_COMMAND="<kubeadm join 命令>" bash /tmp/install_k8s_agent.sh

set -e
LOG_FILE="/tmp/k8s_agent_install.log"
exec > >(tee -a ${LOG_FILE}) 2>&1

echo "================================================"
echo ">>> Kubernetes Agent 安装开始 (全国内源版)"
echo "================================================"

# ===============================================
# 1. 变量定义与校验
# ===============================================
K8S_VERSION=${K8S_VERSION:-""}

if [ -z "$K8S_VERSION" ]; then
    echo "!!! 致命错误: 环境变量 K8S_VERSION 未设置"
    exit 1
fi

echo ">>> 目标版本: ${K8S_VERSION}"
echo ">>> 日志文件: ${LOG_FILE}"

# ==================================================
# 2. 系统源全面修复 (CentOS + EPEL)
# ==================================================
echo ">>> [1/7] 修复系统源配置 (CentOS + EPEL 阿里云镜像)..."
OS_RELEASE=""
if [ -f /etc/redhat-release ]; then
    if grep -q "CentOS Linux 7" /etc/os-release 2>/dev/null || grep -q "CentOS Linux release 7" /etc/redhat-release 2>/dev/null; then
        OS_RELEASE="centos7"
        echo "检测到 CentOS 7，配置阿里云镜像源..."

        # 备份原始源
        BACKUP_DIR="/etc/yum.repos.d/backup_$(date +%Y%m%d_%H%M%S)"
        mkdir -p $BACKUP_DIR
        cp /etc/yum.repos.d/*.repo $BACKUP_DIR/ 2>/dev/null || true
        echo "原始源文件已备份至: $BACKUP_DIR"

        # 清理现有repo文件
        rm -f /etc/yum.repos.d/*.repo

        # 配置CentOS 7 Base源 (阿里云)
        cat <<EOF > /etc/yum.repos.d/CentOS-Base.repo
[base]
name=CentOS-\$releasever - Base - mirrors.aliyun.com
baseurl=https://mirrors.aliyun.com/centos/\$releasever/os/\$basearch/
gpgcheck=1
gpgkey=https://mirrors.aliyun.com/centos/RPM-GPG-KEY-CentOS-7
enabled=1

[updates]
name=CentOS-\$releasever - Updates - mirrors.aliyun.com
baseurl=https://mirrors.aliyun.com/centos/\$releasever/updates/\$basearch/
gpgcheck=1
gpgkey=https://mirrors.aliyun.com/centos/RPM-GPG-KEY-CentOS-7
enabled=1

[extras]
name=CentOS-\$releasever - Extras - mirrors.aliyun.com
baseurl=https://mirrors.aliyun.com/centos/\$releasever/extras/\$basearch/
gpgcheck=1
gpgkey=https://mirrors.aliyun.com/centos/RPM-GPG-KEY-CentOS-7
enabled=1

[centosplus]
name=CentOS-\$releasever - Plus - mirrors.aliyun.com
baseurl=https://mirrors.aliyun.com/centos/\$releasever/centosplus/\$basearch/
gpgcheck=1
gpgkey=https://mirrors.aliyun.com/centos/RPM-GPG-KEY-CentOS-7
enabled=0
EOF

        # 配置EPEL 7源 (阿里云镜像) - 解决超时问题
        cat <<EOF > /etc/yum.repos.d/epel.repo
[epel]
name=Extra Packages for Enterprise Linux 7 - \$basearch
baseurl=https://mirrors.aliyun.com/epel/7/\$basearch
failovermethod=priority
enabled=1
gpgcheck=1
gpgkey=https://mirrors.aliyun.com/epel/RPM-GPG-KEY-EPEL-7

[epel-debuginfo]
name=Extra Packages for Enterprise Linux 7 - \$basearch - Debug
baseurl=https://mirrors.aliyun.com/epel/7/\$basearch/debug
failovermethod=priority
enabled=0
gpgkey=https://mirrors.aliyun.com/epel/RPM-GPG-KEY-EPEL-7
gpgcheck=1

[epel-source]
name=Extra Packages for Enterprise Linux 7 - \$basearch - Source
baseurl=https://mirrors.aliyun.com/epel/7/SRPMS
failovermethod=priority
enabled=0
gpgkey=https://mirrors.aliyun.com/epel/RPM-GPG-KEY-EPEL-7
gpgcheck=1
EOF

        # 导入EPEL GPG密钥
        echo "导入EPEL GPG密钥..."
        rpm --import https://mirrors.aliyun.com/epel/RPM-GPG-KEY-EPEL-7 2>/dev/null || true

        yum clean all
        yum makecache fast

        echo ">>> 系统源配置完成"
        echo ">>> Base源: mirrors.aliyun.com/centos/"
        echo ">>> EPEL源: mirrors.aliyun.com/epel/"
    else
        echo "仅支持 CentOS 7 系统自动配置"
        OS_RELEASE="unknown"
    fi
else
    echo "非 CentOS/RHEL 系统，跳过源配置..."
fi

# ==================================================
# 3. 依赖工具检查
# ==================================================
echo ">>> [2/7] 检查安装依赖工具..."
if [ "$OS_RELEASE" = "centos7" ]; then
    yum install -y wget curl yum-utils device-mapper-persistent-data lvm2 ipvsadm ipset sysstat conntrack-tools

    # 验证EPEL源工作正常
    echo "验证EPEL源..."
    if yum list available --disablerepo="*" --enablerepo="epel" | head -5; then
        echo ">>> EPEL源验证成功"
    else
        echo "!!! 警告: EPEL源可能有问题，尝试备用方案..."
        # 备用EPEL安装方式
        if [ ! -f /etc/yum.repos.d/epel.repo ]; then
            wget -O /tmp/epel-release.rpm https://mirrors.aliyun.com/epel/epel-release-latest-7.noarch.rpm
            rpm -Uvh /tmp/epel-release.rpm
            # 修改epel.repo使用阿里云镜像
            sed -i 's|^#baseurl|baseurl|g' /etc/yum.repos.d/epel.repo
            sed -i 's|^metalink|#metalink|g' /etc/yum.repos.d/epel.repo
            sed -i 's|^baseurl=.*://download.fedoraproject.org/pub|baseurl=https://mirrors.aliyun.com|g' /etc/yum.repos.d/epel.repo
            yum clean all
            yum makecache
        fi
    fi
fi

# ==================================================
# 4. 系统环境初始化
# ==================================================
echo ">>> [3/7] 初始化系统配置..."
swapoff -a
sed -i '/swap/d' /etc/fstab

setenforce 0 2>/dev/null || true
sed -i 's/^SELINUX=enforcing$/SELINUX=permissive/' /etc/selinux/config 2>/dev/null || true

systemctl stop firewalld 2>/dev/null || true
systemctl disable firewalld 2>/dev/null || true

# 清理旧的Kubernetes配置
echo "清理旧的Kubernetes配置..."
kubeadm reset -f 2>/dev/null || true
systemctl stop kubelet 2>/dev/null || true
rm -rf /etc/kubernetes/* 2>/dev/null || true
rm -rf ~/.kube 2>/dev/null || true

echo ">>> 配置内核参数..."
cat <<EOF | tee /etc/modules-load.d/k8s.conf
overlay
br_netfilter
EOF

modprobe overlay
modprobe br_netfilter

cat <<EOF | tee /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
EOF
sysctl --system

# ==================================================
# 5. 安装 Containerd (阿里云镜像)
# ==================================================
echo ">>> [4/7] 安装 Containerd..."
if [ "$OS_RELEASE" = "centos7" ]; then
    echo "配置阿里云 Docker 源..."
    if [ ! -f /etc/yum.repos.d/docker-ce.repo ]; then
        yum-config-manager --add-repo https://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo
    fi

    # 更新缓存
    yum clean expire-cache
    yum makecache

    echo "安装 containerd.io..."
    if ! yum install -y containerd.io; then
        echo "!!! 第一次安装失败，尝试备用方案..."
        # 尝试直接下载rpm包安装
        wget -O /tmp/containerd.io.rpm https://mirrors.aliyun.com/docker-ce/linux/centos/7/x86_64/stable/Packages/containerd.io-1.6.28-3.1.el7.x86_64.rpm 2>/dev/null || \
        wget -O /tmp/containerd.io.rpm https://download.docker.com/linux/centos/7/x86_64/stable/Packages/containerd.io-1.6.28-3.1.el7.x86_64.rpm 2>/dev/null

        if [ -f /tmp/containerd.io.rpm ]; then
            rpm -ivh /tmp/containerd.io.rpm
        else
            echo "!!! 致命错误: 无法获取containerd.io包"
            exit 1
        fi
    fi

    echo "配置 containerd..."
    mkdir -p /etc/containerd
    containerd config default > /etc/containerd/config.toml 2>/dev/null || \
    cat <<EOF > /etc/containerd/config.toml
version = 2
root = "/var/lib/containerd"
state = "/run/containerd"
oom_score = 0

[grpc]
  address = "/run/containerd/containerd.sock"

[plugins]
  [plugins."io.containerd.grpc.v1.cri"]
    sandbox_image = "registry.aliyuncs.com/google_containers/pause:3.9"
    [plugins."io.containerd.grpc.v1.cri".containerd]
      default_runtime_name = "runc"
    [plugins."io.containerd.grpc.v1.cri".registry]
      [plugins."io.containerd.grpc.v1.cri".registry.mirrors]
        [plugins."io.containerd.grpc.v1.cri".registry.mirrors."docker.io"]
          endpoint = ["https://registry-1.docker.io"]
EOF

    # 启用systemd cgroup驱动
    sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml 2>/dev/null || true

    # 配置镜像加速器
    if grep -q "registry.mirrors" /etc/containerd/config.toml 2>/dev/null; then
        sed -i 's|https://registry-1.docker.io|https://registry.aliyuncs.com|g' /etc/containerd/config.toml
    fi

    systemctl daemon-reload
    systemctl enable containerd
    systemctl restart containerd

    echo "验证 containerd 状态..."
    if systemctl status containerd --no-pager | grep -q "active (running)"; then
        echo ">>> Containerd 安装成功"
    else
        echo "!!! 警告: Containerd 服务可能未正常运行"
        systemctl status containerd --no-pager
    fi
fi

# ==================================================
# 6. 安装 Kubernetes 组件 (阿里云镜像)
# ==================================================
echo ">>> [5/7] 安装 Kubernetes 组件..."
if [ "$OS_RELEASE" = "centos7" ]; then
    K8S_REPO_FILE="/etc/yum.repos.d/kubernetes.repo"

    echo "配置阿里云 Kubernetes 源..."
    cat <<EOF > $K8S_REPO_FILE
[kubernetes]
name=Kubernetes
baseurl=https://mirrors.aliyun.com/kubernetes/yum/repos/kubernetes-el7-x86_64/
enabled=1
gpgcheck=0
repo_gpgcheck=0
gpgkey=https://mirrors.aliyun.com/kubernetes/yum/doc/yum-key.gpg
       https://mirrors.aliyun.com/kubernetes/yum/doc/rpm-package-key.gpg
EOF

    # 导入GPG密钥
    yum clean all
    yum makecache

    echo "检查可用版本..."
    yum list kubelet --showduplicates | grep -E "^kubelet\." | sort -r | head -10

    # 安装指定版本
    echo "安装 Kubernetes $K8S_VERSION..."
    if yum install -y kubelet-$K8S_VERSION kubeadm-$K8S_VERSION kubectl-$K8S_VERSION --disableexcludes=kubernetes; then
        echo ">>> Kubernetes 组件安装成功"
    else
        echo "!!! 指定版本安装失败，尝试安装最新可用版本..."
        # 尝试安装最新版本
        yum install -y kubelet kubeadm kubectl --disableexcludes=kubernetes

        # 检查实际安装的版本
        INSTALLED_VERSION=$(kubelet --version | awk '{print $2}')
        echo ">>> 实际安装版本: $INSTALLED_VERSION"

        if [ "$K8S_VERSION" != "${INSTALLED_VERSION#v}" ]; then
            echo "!!! 警告: 安装版本 ($INSTALLED_VERSION) 与目标版本 ($K8S_VERSION) 不匹配"
            echo "!!! 可能导致与Master节点版本不兼容"
        fi
    fi

    systemctl enable kubelet
    systemctl start kubelet

    echo "配置 kubelet 使用国内镜像..."
    mkdir -p /etc/systemd/system/kubelet.service.d
    cat <<EOF > /etc/systemd/system/kubelet.service.d/10-kubeadm.conf
[Service]
Environment="KUBELET_KUBECONFIG_ARGS=--bootstrap-kubeconfig=/etc/kubernetes/bootstrap-kubelet.conf --kubeconfig=/etc/kubernetes/kubelet.conf"
Environment="KUBELET_CONFIG_ARGS=--config=/var/lib/kubelet/config.yaml"
Environment="KUBELET_EXTRA_ARGS=--pod-infra-container-image=registry.aliyuncs.com/google_containers/pause:3.9"
ExecStart=
ExecStart=/usr/bin/kubelet \$KUBELET_KUBECONFIG_ARGS \$KUBELET_CONFIG_ARGS \$KUBELET_EXTRA_ARGS
EOF

    systemctl daemon-reload
    systemctl restart kubelet
fi


echo ""
echo "================================================"
echo ">>> 📋 安装完成总结"
echo "================================================"
echo "1. 系统源: 阿里云镜像 (CentOS + EPEL)"
echo "2. 容器运行时: Containerd (阿里云Docker源)"
echo "3. Kubernetes: 版本 ${K8S_VERSION} (阿里云K8s源)"
echo "4. 镜像仓库: registry.aliyuncs.com/google_containers"
echo "5. 日志文件: ${LOG_FILE}"
echo ""
echo ">>> 验证命令:"
echo "   systemctl status containerd"
echo "   systemctl status kubelet"
echo "   ctr images ls"
echo "================================================"