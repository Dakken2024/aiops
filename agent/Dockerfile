# 使用官方 Python 轻量版
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量，防止 Python 生成 pyc 文件和缓冲日志
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 安装系统依赖
# nsenter 通常包含在 util-linux 包中
RUN apt-get update && apt-get install -y \
    util-linux \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制脚本文件
COPY k8s_agent.py .

# 启动命令
CMD ["python", "k8s_agent.py"]