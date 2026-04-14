# agent/k8s_agent.py
import time, json, os, socket, psutil, subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer

# === 配置 ===
LISTEN_PORT = 10055  # K8s Agent 监听端口 (区分于 ECS 的 10050)
NODE_NAME = os.getenv("NODE_NAME", socket.gethostname())


def run_host_cmd(cmd):
    """通过 nsenter 进入宿主机命名空间执行命令"""
    full_cmd = f"nsenter -t 1 -m -u -i -n {cmd}"
    try:
        res = subprocess.run(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        return res.stdout.decode('utf-8', errors='ignore').strip()
    except:
        return ""


class MetricsHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return  # 静默模式

    def do_GET(self):
        if self.path != '/metrics':
            self.send_response(404)
            self.end_headers()
            return

        try:
            # === 1. 第一次采样 ===
            n1 = psutil.net_io_counters()
            d1 = psutil.disk_io_counters()

            # 阻塞 1 秒 (计算速率)
            time.sleep(1)

            # === 2. 第二次采样 ===
            n2 = psutil.net_io_counters()
            d2 = psutil.disk_io_counters()

            # === 3. 计算指标 ===
            data = {
                "node_name": NODE_NAME,
                "cpu": psutil.cpu_percent(interval=None),
                "mem": psutil.virtual_memory().percent,
                "disk": psutil.disk_usage('/').percent,

                # 速率 (KB/s)
                "net_in": round((n2.bytes_recv - n1.bytes_recv) / 1024, 2),
                "net_out": round((n2.bytes_sent - n1.bytes_sent) / 1024, 2),
                "disk_read_rate": round((d2.read_bytes - d1.read_bytes) / 1024, 2),
                "disk_write_rate": round((d2.write_bytes - d1.write_bytes) / 1024, 2),

                # 日志抓取 (实时)
                "kubelet_log": run_host_cmd("journalctl -u kubelet -n 50 --no-pager"),
                "proxy_log": run_host_cmd("journalctl -u kube-proxy -n 50 --no-pager"),
                "runtime_status": run_host_cmd("systemctl status containerd || systemctl status docker")
            }

            # === 4. 返回 JSON ===
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())

        except Exception as e:
            self.send_response(500)
            self.wfile.write(str(e).encode())


def run():
    server_address = ('0.0.0.0', LISTEN_PORT)
    httpd = HTTPServer(server_address, MetricsHandler)
    print(f"K8s Agent Listening on {LISTEN_PORT}...")
    httpd.serve_forever()


if __name__ == "__main__":
    run()