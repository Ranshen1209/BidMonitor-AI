FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 基础工具 + CloakBrowser/Chromium 运行依赖
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       gcc curl \
       libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
       libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
       libgbm1 libasound2 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt

# 预下载 CloakBrowser 专用 Chromium(约200MB)并缓存进镜像层;失败不阻断构建
RUN python -c "import cloakbrowser; b=cloakbrowser.launch(headless=True); b.close(); print('cloakbrowser binary ready')" || true

COPY src src
COPY server server
COPY README.md README.md

RUN mkdir -p data logs

EXPOSE 8080

CMD ["python", "server/app.py"]
