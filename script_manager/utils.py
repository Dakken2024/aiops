import uuid
import paramiko
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.utils import timezone
from django.db import connections

# 引入模型
from .models import ScriptLog


def append_log(log_id, message):
    """
    辅助函数：原子性追加日志到数据库
    """
    # 这里的锁不是必须的（因为 SQLite/MySQL 有内部锁），但在高并发下
    # 重新获取对象再保存是防止覆盖内容的最好习惯
    try:
        # 必须重新从数据库读取最新状态，否则会覆盖掉其他线程写入的内容
        log_obj = ScriptLog.objects.get(id=log_id)
        if not log_obj.output:
            log_obj.output = ""

        # 追加新内容
        log_obj.output += message
        log_obj.save()
    except Exception as e:
        print(f"日志写入失败: {e}")


def _execute_single_server(log_id, server, script_content, script_type):
    """
    单台服务器执行逻辑
    """
    client = None
    sftp = None
    remote_path = ""

    try:
        # === 阶段 1: 尝试连接 ===
        append_log(log_id, f"[{server.hostname}] 正在连接 SSH...\n")

        if not server.username or not server.password:
            append_log(log_id, f"[{server.hostname}] ❌ 跳过：未配置账号密码\n")
            return

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=server.ip_address,
            port=server.port,
            username=server.username,
            password=server.password,
            timeout=5,  # 连接超时 5秒
            banner_timeout=5
        )

        # === 阶段 2: 上传脚本 ===
        # append_log(log_id, f"[{server.hostname}] 连接成功，正在上传脚本...\n") # 可选，嫌啰嗦可注释

        file_ext = '.py' if script_type == 'py' else '.shell'
        file_name = f"ops_{uuid.uuid4().hex}{file_ext}"
        remote_path = f"/tmp/{file_name}"

        sftp = client.open_sftp()
        with sftp.open(remote_path, 'w') as f:
            # 统一换行符
            clean_content = script_content.replace('\r\n', '\n')
            f.write(clean_content)

        client.exec_command(f"chmod +x {remote_path}")

        # === 阶段 3: 执行脚本 ===
        interpreter = '/usr/bin/python3' if script_type == 'py' else '/bin/bash'
        exec_cmd = f"{interpreter} -u {remote_path}" if script_type == 'py' else f"{remote_path}"

        append_log(log_id, f"[{server.hostname}] 脚本已上传，开始执行...\n")

        # 注意：这里依然会阻塞直到脚本跑完，但我们之前已经输出了“开始执行”
        # 如果脚本非常长，建议检查脚本本身是否包含 sleep 或死循环
        stdin, stdout, stderr = client.exec_command(exec_cmd, timeout=300)

        out_str = stdout.read().decode('utf-8', errors='replace').strip()
        err_str = stderr.read().decode('utf-8', errors='replace').strip()

        # === 阶段 4: 输出结果 ===
        now_str = timezone.now().strftime('%H:%M:%S')
        result_msg = f"\n[{now_str}] @ {server.hostname} 执行结束:\n"
        if out_str: result_msg += f"{out_str}\n"
        if err_str: result_msg += f"ERROR output:\n{err_str}\n"
        if not out_str and not err_str: result_msg += "(Success, No Output)\n"
        result_msg += ("-" * 40) + "\n"

        append_log(log_id, result_msg)

    except Exception as e:
        append_log(log_id, f"[{server.hostname}] ❌ 异常: {str(e)}\n" + ("-" * 40) + "\n")

    finally:
        # === 清理 ===
        try:
            if client and remote_path:
                client.exec_command(f"rm -f {remote_path}")
        except:
            pass
        if sftp: sftp.close()
        if client: client.close()


def run_task_in_background(log_id, script_content, script_type, servers):
    """
    后台管理线程
    """
    connections.close_all()  # 清理旧连接

    try:
        # 初始化日志
        append_log(log_id, f"任务启动，共 {len(servers)} 台服务器，正在并行执行...\n{'=' * 40}\n")

        with ThreadPoolExecutor(max_workers=10) as executor:
            # 这里的区别是：我们把 log_id 传进去了，让子线程自己去写日志
            # 这样用户就能看到“正在连接”、“正在执行”的过程
            futures = [
                executor.submit(_execute_single_server, log_id, s, script_content, script_type)
                for s in servers
            ]

            # 等待所有任务结束
            for future in as_completed(futures):
                pass  # 结果已经在 _execute_single_server 里写了，这里不需要做处理

        # 标记最终完成
        final_log = ScriptLog.objects.get(id=log_id)
        final_log.status = 'success'
        final_log.end_time = timezone.now()
        final_log.output += "\n[System]: 所有任务执行完毕。"
        final_log.save()

    except Exception as e:
        error_log = ScriptLog.objects.get(id=log_id)
        error_log.status = 'failed'
        error_log.output += f"\n[System Error]: {str(e)}"
        error_log.save()
    finally:
        connections.close_all()