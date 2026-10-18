FROM node:22-alpine AS web-builder
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- 构建阶段：装依赖进独立 venv，避免把 pip 缓存/编译工具带进运行镜像 ----
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# YOLO 是可选重依赖（含 torch，1GB+）：默认不装，构建参数打开才装
ARG INSTALL_YOLO=false
COPY backend/requirements-model.txt .
COPY backend/ultralytics ./ultralytics
RUN if [ "$INSTALL_YOLO" = "true" ]; then \
        pip install --no-cache-dir -r requirements-model.txt \
        && pip install --no-cache-dir -e ./ultralytics; \
    fi

# ---- 运行阶段：只带 venv 和代码，不带 pip 缓存与编译链 ----
FROM python:3.12-slim

# 中文字体：标注框上的虫种名是中文，缺字体时 annotate.py 会退化成
# ASCII 兜底（历史上是字面量 "pest"），演示视频的标注全变成 "pest 92%"。
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin pestguard

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY backend/app ./app
COPY backend/alembic.ini .
COPY backend/alembic ./alembic
COPY backend/static ./static
# The API serves the same React build as the optional standalone web container.
COPY --from=web-builder /web/dist /frontend/dist
# 自带的定制 ultralytics 运行时（yolov12 / GSConv 改动）。
# 必须放进运行镜像：构建阶段是 pip install -e（editable），
# 记录的是构建阶段里 /ultralytics 这个绝对路径，而运行阶段并没有它，
# 于是容器里 `import ultralytics` 必然失败 —— 更要命的是
# detector.warmup() 会把 ModuleNotFoundError 吞掉，/api/health 仍返回
# status=ok（只是 detector_ready=false），健康检查照过，
# 评委第一次上传才 500。所以这里显式把包带过来，并在构建期就验证可导入。
ARG INSTALL_YOLO=false
COPY backend/ultralytics ./ultralytics
# PYTHONPATH 显式指向 /app，让 `import ultralytics` 命中自带的这份，
# 而不依赖"CWD 刚好在 sys.path 里"这个隐含前提。
ENV PYTHONPATH=/app
RUN if [ "$INSTALL_YOLO" = "true" ]; then \
        python -c "import ultralytics; print('ultralytics import OK:', ultralytics.__file__)"; \
    fi
# 运行时必需的只读数据：RAG 知识库与寄主先验表。
# 缺了这两个，容器里「引用溯源」与寄主先验会静默失效，而 /api/health 看不出来。
# 只拷这两个，不整个拷 data/：uploads/results 是用户数据，不该进镜像。
#
# 顺序要求：必须放在下面那条 mkdir ... && chown ... 之前。
# COPY 落地的新文件属主是 root，若先chown 再 COPY，
# 业务进程（USER pestguard，非root）就读不了这两个文件，知识库又白拷了。
COPY backend/data/host_prior.json ./data/host_prior.json
COPY backend/data/knowledge ./data/knowledge
RUN mkdir -p /app/data/uploads /app/data/results && chown -R pestguard:pestguard /app/data

# 不用 root 跑业务进程：即使应用被攻破，攻击者拿到的也只是普通用户
USER pestguard

EXPOSE 8000
# 迁移在启动前执行；--timeout 120 给迁移和首包留足时间
CMD ["sh", "-c", "alembic upgrade head && exec gunicorn app.main:app -k uvicorn.workers.UvicornWorker --workers 1 --timeout 120 --bind 0.0.0.0:8000"]
