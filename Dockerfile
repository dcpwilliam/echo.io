# aiservice · 零依赖 Python 服务（标准库即可，含 sqlite3）
FROM python:3.11-slim

WORKDIR /app

# 拷贝依赖清单（当前为空，仅占位，便于将来扩展）
COPY requirements.txt /app/

# 拷贝整个 aiservice 源码
COPY . /app/

# 非 root 运行，提高安全性
RUN groupadd -r aiservice && useradd -r -g aiservice -d /app aiservice \
    && mkdir -p /app/data && chown -R aiservice:aiservice /app
USER aiservice

ENV AISERVICE_HOST=0.0.0.0 \
    AISERVICE_PORT=8100 \
    AISERVICE_STORAGE=sqlite \
    AISERVICE_DATA_DIR=/app/data

EXPOSE 8100

# 探活：标准库 urllib，无需 curl
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8100/health').status==200 else 1)"

CMD ["python", "run.py", "--host", "0.0.0.0", "--port", "8100"]
