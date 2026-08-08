# AI Interpreter 后端容器镜像
# 依赖使用 requirements.lock.txt 锁定，确保可复现。
FROM python:3.11-slim

WORKDIR /app

# 避免 Python 输出缓冲导致日志延迟
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.lock.txt ./backend/requirements.lock.txt
COPY requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.lock.txt

COPY backend/ ./backend/
WORKDIR /app/backend

# 默认仅监听本机回环；容器网络隔离下由编排层映射端口。
ENV HOST=0.0.0.0 \
    REDIS_URL=redis://localhost:6379/0

EXPOSE 8000

CMD ["python", "main.py"]
