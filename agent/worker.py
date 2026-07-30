"""单店铺 worker：轮询 DB 取本店铺待执行任务，串行执行。

容器化部署模型：
  - 每个店铺一个 worker 容器（docker-compose 的 worker-* 服务）
  - 通过 --shop 参数或 TARGET_SHOP 环境变量绑定
  - 串行执行任务（单店铺同时仅 1 个任务，避免风控）
  - 空闲时按 POLL_INTERVAL 秒轮询

与 API 层的关系：
  - 开发模式：API 进程内 inline 执行任务（create_task 直接 asyncio.create_task）
  - 容器模式：API 只创建任务记录（EXECUTION_MODE=worker），worker 容器轮询执行

用法：
  python -m agent.worker --shop shop_taobao
  TARGET_SHOP=shop_pinduoduo python -m agent.worker
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.runner import run_task
from agent.state import TaskStatus
from data.repositories.task_repo import TaskRepo

logger = logging.getLogger(__name__)

POLL_INTERVAL = 5  # 秒：无任务时的轮询间隔


class Worker:
    def __init__(self, shop_id: str, poll_interval: int = POLL_INTERVAL):
        self.shop_id = shop_id
        self.poll_interval = poll_interval
        self._stop = False

    def stop(self, *_):
        logger.info("[worker:%s] 收到停止信号，等待当前任务完成后退出", self.shop_id)
        self._stop = True

    def run_forever(self):
        logger.info("[worker:%s] 启动，轮询间隔 %ds", self.shop_id, self.poll_interval)
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)
        while not self._stop:
            try:
                task_id = TaskRepo().claim_next_pending(self.shop_id)
                if not task_id:
                    time.sleep(self.poll_interval)
                    continue
                self._execute_one(task_id)
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.exception("[worker:%s] 轮询异常: %s", self.shop_id, e)
                time.sleep(self.poll_interval)
        logger.info("[worker:%s] 已退出", self.shop_id)

    def _execute_one(self, task_id: str):
        """执行单个任务。run_task 内部已处理状态同步与日志归档。"""
        task = TaskRepo().get(task_id)
        if not task:
            logger.warning("[worker:%s] 任务 %s 不存在，跳过", self.shop_id, task_id)
            return
        product_code = task.get("product_code", "")
        logger.info("[worker:%s] 领取任务 %s (product=%s)",
                    self.shop_id, task_id, product_code)
        try:
            final = run_task(task_id, product_code, self.shop_id)
            status = final.get("status", TaskStatus.FAILED.value)
            logger.info("[worker:%s] 任务 %s 完成，终态=%s",
                        self.shop_id, task_id, status)
        except Exception as e:
            logger.exception("[worker:%s] 任务 %s 执行异常: %s",
                             self.shop_id, task_id, e)
            TaskRepo().update_status(
                task_id, TaskStatus.FAILED.value,
                error_msg=f"worker 异常: {e}", finished=True,
            )


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    ap = argparse.ArgumentParser(description="单店铺任务执行 worker")
    ap.add_argument("--shop", default=os.environ.get("TARGET_SHOP", ""),
                    help="绑定的店铺 ID（缺省读 TARGET_SHOP 环境变量）")
    ap.add_argument("--poll", type=int, default=POLL_INTERVAL,
                    help="无任务时轮询间隔（秒）")
    args = ap.parse_args()

    if not args.shop:
        print("ERROR: 必须指定 --shop 或设置 TARGET_SHOP 环境变量", file=sys.stderr)
        sys.exit(1)

    # 校验店铺配置存在
    from config.settings import get_config
    if args.shop not in get_config().shops:
        print(f"ERROR: 店铺 {args.shop} 未在 config/shops/*.yaml 配置", file=sys.stderr)
        sys.exit(1)

    worker = Worker(args.shop, poll_interval=args.poll)
    worker.run_forever()


if __name__ == "__main__":
    main()
