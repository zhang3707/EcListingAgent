# 电商商品上下架智能 Agent 运行镜像
#
# 基础镜像选型说明：
#   官方 playwright/python:v1.45.0-jammy 内置 Python 3.10，不满足 requires-python>=3.11，
#   且未预装 python3-venv（ensurepip 缺失）。故改用 python:3.11-slim 作为基础，
#   通过 `playwright install --with-deps chromium` 一次性安装 Chromium 浏览器与系统依赖。
#
# 多阶段构建：builder 阶段安装 Python 依赖（利用层缓存），runtime 阶段只拷必要产物。
FROM python:3.11-slim AS builder

# 构建期参数：是否安装 dev 依赖（训练/测试）。生产镜像用 --build-arg INSTALL_DEV=0
ARG INSTALL_DEV=0

WORKDIR /build

# 先拷依赖清单与 config（config 为 package 之一，使 packages.find 可解析元数据），
# 利用 Docker 层缓存：源码变更不会触发依赖重装。
COPY pyproject.toml ./
COPY config/ ./config/
# pyproject.toml 的 readme 字段引用 README.md，setuptools 构建元数据时需存在；
# 用占位文件满足解析，避免真实 README 变更触发依赖重装（真实 README 在 runtime 阶段从上下文拷入）。
RUN touch README.md

# 装依赖到 /opt/venv（独立虚拟环境，便于 runtime 阶段整体拷贝）
# 预装 CPU-only torch：默认 Linux torch 会拉取 ~4GB CUDA 库（nvidia-cudnn/cublas/nccl），
# 容器内无 GPU 完全无用且严重膨胀镜像。先装 CPU 版，后续 ultralytics 发现 torch 已满足即跳过。
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && if [ "$INSTALL_DEV" = "1" ]; then \
         /opt/venv/bin/pip install --no-cache-dir -e ".[dev]"; \
       else \
         /opt/venv/bin/pip install --no-cache-dir -e .; \
       fi


# ---- runtime 阶段 ----
FROM python:3.11-slim AS runtime

# 拷虚拟环境（含全部 Python 依赖）
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# 安装 Chromium + 系统依赖（--with-deps 自动 apt install 所需库）+ 中文字体；
# 创建数据持久化目录。
# 注意：此层重量级（~130MB Chromium），置于源码 COPY 之前，避免代码变更触发重下载。
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/* \
    && playwright install --with-deps chromium \
    && mkdir -p data_persist/browser_profiles data_persist/fingerprints \
                 data_persist/slider_model logs/feishu_fallback

# 拷源码（runtime 以 /app 为 CWD，flat package 经 sys.path[0] 解析）
# 位于重依赖层之后：代码变更只 invalidated 这些轻量 COPY 层，不触发 Chromium 重装。
COPY --from=builder /build/pyproject.toml ./
COPY README.md ./
COPY agent/ ./agent/
COPY skills/ ./skills/
COPY engine/ ./engine/
COPY data/ ./data/
COPY integrations/ ./integrations/
COPY api/ ./api/
COPY config/ ./config/
COPY scripts/ ./scripts/
COPY entrypoint.sh ./

RUN chmod +x entrypoint.sh

# 滑块模型：构建期预下载（若 data_persist 已有则 COPY 覆盖）
# 生产构建建议挂载卷或 CI 预训练后拷入，避免镜像过大
# COPY data_persist/slider_gap_yolov8n.pt data_persist/

EXPOSE 8000

# 角色化入口：ROLE=api（默认）/ worker / migrate
# api/worker 由 docker-compose 通过 ROLE 环境变量切换，无需 command 覆盖
ENTRYPOINT ["./entrypoint.sh"]
