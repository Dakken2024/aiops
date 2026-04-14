import os
import paramiko
import logging
from celery import shared_task
from concurrent.futures import ThreadPoolExecutor, as_completed
from cmdb.models import Server  # 假设 CMDB Model 路径正确

logger = logging.getLogger('k8s_manager')


def get_install_script_content():
    """
    读取 k8s_manager/shell/install_k8s.sh 文件内容。
    注意：在实际部署中，请确保 'shell/install_k8s.sh' 路径相对于 tasks.py 是正确的。
    """
    try:
        # 尝试查找 shell/install_k8s.sh
        current_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(current_dir, 'shell', 'install_k8s.sh')

        if not os.path.exists(script_path):
            # 如果 shell/ 不存在，尝试 k8s_manager/install_k8s.sh (兼容你的上传文件结构)
            script_path = os.path.join(current_dir, 'install_k8s.sh')
            if not os.path.exists(script_path):
                logger.error(f"Install script not found at: {script_path}")
                return None

        with open(script_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error(f"读取安装脚本失败: {e}")
        return None


def install_node_worker(server_id, join_command, auto_install, script_content, k8s_version):
    """
    [子线程任务] 单个节点的 SSH 安装与 Join 逻辑。
    此函数在 ThreadPoolExecutor 中运行，不能调用 self.update_state()。

    Returns:
        str: 包含执行结果（成功/失败）和日志的字符串。
    """
    try:
        server = Server.objects.get(id=server_id)
    except Server.DoesNotExist:
        return f"[Server Error] ID {server_id} not found"

    hostname = server.hostname
    ip = server.ip_address
    log_prefix = f"[{hostname} / {ip}]"

    client = None
    full_log = ""
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        pwd = str(server.password) if server.password else None

        client.connect(
            hostname=ip,
            port=server.port,
            username=server.username,
            password=pwd,
            timeout=20
        )
        full_log += f"{log_prefix} SSH连接成功。\n"

        # 1. 强制修改主机名 (确保主机名正确设置)
        client.exec_command(f"sudo hostnamectl set-hostname {hostname}")
        client.exec_command(f"echo '127.0.0.1 {hostname}' | sudo tee -a /etc/hosts")

        # 2. 自动安装环境
        if auto_install and script_content:
            full_log += f"{log_prefix} 开始环境初始化 (K8s Version: {k8s_version})...\n"

            client.exec_command("sudo kubeadm reset -f")
            client.exec_command("sudo systemctl stop kubelet")

            # 上传脚本
            sftp = client.open_sftp()
            with sftp.file("/tmp/install_k8s.sh", "w") as f:
                f.write(script_content)
            sftp.close()
            full_log += f"{log_prefix} 安装脚本上传至 /tmp/install_k8s.sh。\n"

            # 执行安装，传递 K8S_VERSION 环境变量
            remote_cmd = f"sudo K8S_VERSION={k8s_version} bash /tmp/install_k8s.sh"

            stdin, stdout, stderr = client.exec_command(remote_cmd, timeout=900)
            exit_status = stdout.channel.recv_exit_status()

            output = stdout.read().decode().strip()
            err = stderr.read().decode().strip()

            if exit_status != 0:
                full_log += f"{log_prefix} 环境初始化失败:\n{output}\n{err}\n"
                return f"{log_prefix} ❌ 环境初始化失败: {err or output}"

            full_log += f"{log_prefix} 环境初始化成功。\n"

            # 确保 Kubelet 停止并清理配置 (为 Join 预留干净环境)
            client.exec_command("sudo systemctl stop kubelet")
            client.exec_command("sudo kubeadm reset -f")
            client.exec_command("sudo rm -rf /etc/kubernetes/kubelet.conf")
            client.exec_command("sudo rm -rf /etc/kubernetes/pki/ca.crt")

        # 3. 执行 Join
        full_log += f"{log_prefix} 开始执行 Join Command...\n"

        if not auto_install:
            # 非自动安装模式下，进行一次简单检查
            stdin, stdout, stderr = client.exec_command("ls /etc/kubernetes/kubelet.conf", timeout=10)
            if stdout.channel.recv_exit_status() == 0:
                return f"{log_prefix} ❌ 节点已存在 kubelet.conf，请先清理或勾选自动安装。"

        # 执行 Join
        stdin, stdout, stderr = client.exec_command(f"sudo {join_command}", timeout=120)
        exit_status = stdout.channel.recv_exit_status()

        output = stdout.read().decode().strip()
        err = stderr.read().decode().strip()

        if exit_status == 0:
            full_log += f"{log_prefix} Join 成功。\n"
            client.exec_command("sudo systemctl enable --now kubelet")
            return f"{log_prefix} ✅ 成功加入集群"
        else:
            full_log += f"{log_prefix} Join 失败: {err}\n"
            return f"{log_prefix} ❌ Join失败: {err or output}"

    except Exception as e:
        # 捕获 SSH 连接或 Paramiko 异常
        full_log += f"{log_prefix} ❌ 异常: {type(e).__name__} - {str(e)}\n"
        return f"{log_prefix} ❌ 异常: {type(e).__name__} - {str(e)}"
    finally:
        if client:
            try:
                client.close()
            except:
                pass


@shared_task(bind=True)
def k8s_node_add_task(self, server_ids, join_command, auto_install, k8s_version=None):
    """
    [Celery 异步任务] 批量并发执行节点扩容
    主任务 (self) 负责状态更新，子线程 (install_node_worker) 只返回结果。
    """
    logger.info(f"开始执行扩容任务，目标节点数: {len(server_ids)}, 版本: {k8s_version}")

    self.update_state(state='STARTED', meta={'current_log': f"开始初始化 {len(server_ids)} 个节点任务..."})

    script_content = ""
    if auto_install:
        script_content = get_install_script_content()
        if not script_content:
            # 脚本读取失败，直接返回失败信息
            return "错误: 无法读取安装脚本 k8s_manager/shell/install_k8s.sh"

    results = []

    # 包装整个执行块，确保任何错误都被捕获并转换为字符串
    try:
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                # 确保只传递 5 个参数，且顺序正确
                executor.submit(install_node_worker, sid, join_command, auto_install, script_content, k8s_version): sid
                for sid in server_ids
            }

            for future in as_completed(futures):
                # 捕获子线程中的异常，确保返回的是字符串
                try:
                    res = future.result()
                except Exception as e:
                    # 如果子线程本身抛出了未处理的异常，将其转换为字符串日志
                    res = f"[INTERNAL ERROR] 子线程意外失败: {type(e).__name__} - {str(e)}"
                    logger.error(f"子线程发生未预期的异常: {res}")

                results.append(res)

                # 在主 Celery 任务线程中更新状态 (安全)
                self.update_state(state='PROGRESS', meta={'current_log': "\n".join(results)})

    except Exception as e:
        # 捕获主线程并发执行块的意外错误
        summary = "\n".join(results) + f"\n[FATAL] 主任务并发执行失败: {type(e).__name__} - {str(e)}"
        # 即使失败，也通过 return 返回，状态机最终会标记为 SUCCESS/FAILURE，但结果是字符串。
        return summary

    summary = "\n".join(results)

    # 检查是否有任何一个节点失败
    if any("❌" in r for r in results):
        # 发现逻辑失败，我们不抛出异常，而是返回带有失败标记的字符串
        self.update_state(state='PROGRESS', meta={'current_log': summary})
        return f"扩容任务失败，详情:\n{summary}"

    logger.info(f"扩容任务结束:\n{summary}")
    # 任务正常结束，Celery 会自动标记为 SUCCESS
    return f"扩容任务成功完成:\n{summary}"