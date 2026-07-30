#!/bin/sh
# 容器入口脚本：按角色启动不同服务
#   ROLE=api     : 等待 postgres 就绪 → 初始化 DB → 启动 uvicorn
#   ROLE=worker  : 等待 postgres 就绪 → 启动单店铺 worker（需 TARGET_SHOP）
#   ROLE=migrate : 等待 postgres 就绪 → 仅初始化 DB 后退出
#
# docker-compose 已通过 depends_on:condition:service_healthy 保证 postgres 健康检查通过，
# 但此处再做一次应用层连通性探测，确保 schema 可用后再启动业务进程。
set -e

ROLE="${ROLE:-api}"

# 等待 postgres 应用层就绪（最多 60s）
if [ -n "$PG_DSN" ]; then
    echo "[entrypoint] waiting for postgres..."
    for i in $(seq 1 30); do
        if python -c "from data.db import get_engine; get_engine().connect()" 2>/dev/null; then
            echo "[entrypoint] postgres ready"
            break
        fi
        echo "[entrypoint] postgres not ready, retry $i/30..."
        sleep 2
    done
fi

case "$ROLE" in
    migrate)
        echo "[entrypoint] running DB migration..."
        python scripts/init_db.py
        echo "[entrypoint] migration done"
        ;;
    api)
        echo "[entrypoint] initializing DB..."
        python scripts/init_db.py
        echo "[entrypoint] starting API server..."
        exec uvicorn api.server:app --host 0.0.0.0 --port 8000
        ;;
    worker)
        if [ -z "$TARGET_SHOP" ]; then
            echo "[entrypoint] ERROR: TARGET_SHOP not set for worker role"
            exit 1
        fi
        echo "[entrypoint] starting worker for shop=$TARGET_SHOP..."
        exec python -m agent.worker --shop "$TARGET_SHOP"
        ;;
    *)
        echo "[entrypoint] unknown ROLE=$ROLE, fallback to api"
        exec uvicorn api.server:app --host 0.0.0.0 --port 8000
        ;;
esac
