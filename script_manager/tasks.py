from celery import shared_task
from django.utils import timezone
from concurrent.futures import ThreadPoolExecutor
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import TaskExecution, TaskLog
from cmdb.views import get_secure_ssh_client
import socket
import time


@shared_task
def execute_script_task(execution_id):
    """
    批量执行脚本的核心任务 (支持 WebSocket 实时日志流)
    """
    try:
        task = TaskExecution.objects.get(id=execution_id)
    except TaskExecution.DoesNotExist:
        return f"Task {execution_id} not found."

    # 获取 Channel Layer 用于发送实时消息
    channel_layer = get_channel_layer()
    group_name = f"task_{task.id}"

    # --- 辅助函数：推送 WebSocket 消息 ---
    def send_ws_update(server_id, status, log_content=None, exit_code=None):
        """
        构造标准消息格式并广播
        """
        data = {
            'server_id': server_id,
            'status': status,
            'log': log_content,  # 增量日志内容
            'exit_code': exit_code
        }
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "task_update",  # 对应 consumer.py 中的方法名
                "data": data
            }
        )

    # =================================================
    # 1. 脚本内容预处理
    # =================================================
    script_content = task.script.content

    # 强制转换 Windows 换行符
    script_content = script_content.replace('\r\n', '\n')

    # 变量替换
    for key, val in task.params.items():
        script_content = script_content.replace(f"{{{{ {key} }}}}", str(val))
        script_content = script_content.replace(f"{{{{{key}}}}}", str(val))

    # =================================================
    # 2. 定义单机执行逻辑 (闭包函数)
    # =================================================
    def run_one(log_id):
        try:
            log = TaskLog.objects.get(id=log_id)
        except TaskLog.DoesNotExist:
            return 'Failed'

        server = log.server

        # [DB] 更新状态为 Running
        log.status = 'Running'
        log.start_time = timezone.now()
        log.save()

        # [WS] 推送状态：开始运行
        send_ws_update(server.id, 'Running')

        client = None
        remote_path = f"/tmp/ops_script_{task.id}_{log.id}.sh"

        # 用于存储完整日志以保存到数据库
        full_stdout = []
        full_stderr = []

        try:
            # A. 建立 SSH 连接
            client = get_secure_ssh_client(server, timeout=10)

            # B. 上传脚本文件
            sftp = client.open_sftp()
            with sftp.open(remote_path, 'w') as f:
                f.write(script_content)
            sftp.close()

            # C. 构建执行命令
            cmd_exec = f"chmod +x {remote_path} && {remote_path}"
            if task.script.script_type == 'py':
                cmd_exec = f"python3 {remote_path}"

            # D. 执行命令 (开启 get_pty=True 以便模拟终端实时输出，stderr 会合并到 stdout)
            # 如果需要严格区分 stderr，可以设为 False，但实时性读取会复杂一些
            stdin, stdout, stderr = client.exec_command(cmd_exec, get_pty=True)

            # 设置超时
            timeout_val = float(task.timeout) if task.timeout else 60.0
            stdout.channel.settimeout(timeout_val)

            # E. [关键] 实时流式读取输出
            while not stdout.channel.exit_status_ready():
                if stdout.channel.recv_ready():
                    # 读取数据块
                    chunk = stdout.channel.recv(1024).decode('utf-8', errors='ignore')
                    if chunk:
                        full_stdout.append(chunk)
                        # [WS] 实时推送日志片段
                        send_ws_update(server.id, 'Running', log_content=chunk)

                # 短暂休眠避免 CPU 空转
                time.sleep(0.05)

            # 读取缓冲区剩余内容
            if stdout.channel.recv_ready():
                chunk = stdout.channel.recv(1024).decode('utf-8', errors='ignore')
                full_stdout.append(chunk)
                send_ws_update(server.id, 'Running', log_content=chunk)

            # 获取退出码
            exit_code = stdout.channel.recv_exit_status()

            # F. 清理临时文件
            client.exec_command(f"rm -f {remote_path}")

            # G. 保存结果到数据库
            log.stdout = "".join(full_stdout)
            # 由于 get_pty=True，stderr 通常合并在 stdout 中，这里保留字段兼容
            log.stderr = "".join(full_stderr)
            log.exit_code = exit_code
            log.status = 'Success' if exit_code == 0 else 'Failed'

            # [WS] 推送最终状态
            send_ws_update(server.id, log.status, exit_code=exit_code)

        except socket.timeout:
            # 超时处理
            log.status = 'Timeout'
            err_msg = f"\n[System] 执行超时 (限制 {timeout_val} 秒)，任务被强制终止。\n"
            log.stderr = err_msg
            # [WS] 推送错误日志
            send_ws_update(server.id, 'Timeout', log_content=err_msg)

            # 尝试清理进程
            try:
                if client: client.exec_command(f"pkill -f {remote_path}")
            except:
                pass

        except Exception as e:
            # 其他异常
            log.status = 'Failed'
            err_msg = f"\n[System] 执行异常: {str(e)}\n"
            log.stderr = err_msg
            # [WS] 推送异常信息
            send_ws_update(server.id, 'Failed', log_content=err_msg)

        finally:
            # H. 收尾工作
            log.end_time = timezone.now()
            log.save()
            if client:
                client.close()
            return log.status

    # =================================================
    # 3. 并发调度执行
    # =================================================

    pending_log_ids = list(task.logs.filter(status='Pending').values_list('id', flat=True))

    results = []
    if pending_log_ids:
        # 使用线程池并发执行
        with ThreadPoolExecutor(max_workers=task.concurrency) as executor:
            futures = [executor.submit(run_one, log_id) for log_id in pending_log_ids]
            results = [f.result() for f in futures]

    # =================================================
    # 4. 更新主任务最终状态
    # =================================================
    task.success_count = results.count('Success')
    task.failed_count = results.count('Failed') + results.count('Timeout')
    task.end_time = timezone.now()
    task.is_finished = True
    task.save()

    return f"Task {task.id} finished. Success: {task.success_count}, Failed: {task.failed_count}"