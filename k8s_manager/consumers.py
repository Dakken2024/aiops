import json
import threading
from channels.generic.websocket import WebsocketConsumer
from kubernetes import stream
from .utils import get_k8s_client


class K8sShellConsumer(WebsocketConsumer):
    def connect(self):
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            self.close()
            return

        # 解析 URL 参数
        query_string = self.scope['query_string'].decode()
        params = dict(x.split('=') for x in query_string.split('&'))

        self.cluster_id = params.get('cluster_id')
        self.namespace = params.get('namespace')
        self.pod_name = params.get('pod_name')
        self.container = params.get('container')

        try:
            # 1. 获取 K8s 客户端
            v1, _, _, err, _ = get_k8s_client(self.cluster_id)
            if not v1:
                self.close()
                return

            self.accept()

            # 2. 建立 K8s Stream 连接
            # 优先尝试 bash，这在大多数现代镜像中体验更好
            exec_command = ['/bin/shell', '-c', 'TERM=xterm-256color /bin/bash || /bin/shell']

            self.stream = stream.stream(
                v1.connect_get_namespaced_pod_exec,
                self.pod_name,
                self.namespace,
                command=exec_command,
                container=self.container,
                stderr=True, stdin=True,
                stdout=True, tty=True,
                _preload_content=False  # 流式传输关键参数
            )

            # 3. 开启读取线程
            self.thread = threading.Thread(target=self.loop_read)
            self.thread.daemon = True
            self.thread.start()

        except Exception as e:
            # 发送错误信息给前端终端显示
            try:
                self.send(text_data=json.dumps({'data': f'\r\nConnection Error: {str(e)}\r\n'}))
            except:
                pass
            self.close()

    def disconnect(self, close_code):
        """前端断开时，关闭 K8s 连接"""
        if hasattr(self, 'stream') and self.stream:
            try:
                self.stream.close()
            except:
                pass

    def receive(self, text_data):
        """接收前端输入 -> 发送给 K8s"""
        try:
            data = json.loads(text_data)
            msg = data.get('data')

            if msg and hasattr(self, 'stream'):
                if self.stream.is_open():
                    self.stream.write_stdin(msg)
        except:
            pass  # 忽略写入错误

    def loop_read(self):
        """
        [核心修复] 循环读取 K8s 返回的数据
        增加了 try-except 捕获 WinError 10053 和其他连接错误
        """
        try:
            while self.stream.is_open():
                # 1. 更新缓冲区 (这里最容易报错)
                try:
                    self.stream.update(timeout=1)
                except Exception:
                    # 捕获所有 socket 错误 (包括 WinError 10053)，并在出错时退出循环
                    break

                # 2. 读取 stdout
                if self.stream.peek_stdout():
                    out = self.stream.read_stdout()
                    self.send(text_data=json.dumps({'data': out}))

                # 3. 读取 stderr
                if self.stream.peek_stderr():
                    err = self.stream.read_stderr()
                    self.send(text_data=json.dumps({'data': err}))

        except Exception as e:
            # 线程意外退出
            pass
        finally:
            # 无论如何，最后关闭 WebSocket
            self.close()


class K8sLogConsumer(WebsocketConsumer):
    def connect(self):
        self.accept()

        # 从 URL 获取参数
        self.cluster_id = self.scope['url_route']['kwargs']['cluster_id']
        self.namespace = self.scope['url_route']['kwargs']['namespace']
        self.pod_name = self.scope['url_route']['kwargs']['pod_name']
        self.container = None  # 可选：支持多容器

        # 控制线程退出的信号
        self.stop_event = threading.Event()

        # 启动日志读取线程
        self.log_thread = threading.Thread(target=self.stream_logs)
        self.log_thread.daemon = True
        self.log_thread.start()

    def disconnect(self, close_code):
        # 断开连接时停止线程
        self.stop_event.set()

    def receive(self, text_data):
        pass  # 日志流通常是单向的，暂不需要处理前端输入

    def stream_logs(self):
        """后台线程：调用 K8s API 读取流"""
        v1, _, _, err, _ = get_k8s_client(self.cluster_id)
        if err:
            self.send_log(f"Connect Error: {err}")
            return

        try:
            # 相当于 kubectl logs -f
            stream = v1.read_namespaced_pod_log(
                name=self.pod_name,
                namespace=self.namespace,
                follow=True,
                tail_lines=100,
                _preload_content=False  # 关键：不预加载，返回生成器
            )

            for line in stream:
                if self.stop_event.is_set():
                    break
                # K8s 返回的是 bytes，解码并发送
                if line:
                    self.send_log(line.decode('utf-8', errors='ignore'))

            self.send_log("\n[System] Log stream ended.")

        except Exception as e:
            self.send_log(f"\n[System] Stream interrupted: {str(e)}")

    def send_log(self, message):
        """辅助发送方法"""
        try:
            self.send(json.dumps({'data': message}))
        except:
            self.stop_event.set()