FROM python:3.11-slim

# 纯标准库实现，不装任何 pip 依赖
WORKDIR /app

COPY panel/app.py /app/app.py
COPY scripts/leigod_common.py /app/leigod_common.py

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LEIGOD_PANEL_PORT=5788

EXPOSE 5788

HEALTHCHECK --interval=60s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5788/healthz',timeout=4).status==200 else 1)"

CMD ["python3", "/app/app.py"]
