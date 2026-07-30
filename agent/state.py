"""全局工作流状态定义。"""
from __future__ import annotations

from enum import Enum
from typing import Any, TypedDict


class CaptchaType(str, Enum):
    NONE = "none"
    SLIDE = "slide"
    SMS = "sms"


class TaskStatus(str, Enum):
    PENDING = "待执行"
    RUNNING = "执行中"
    SUCCESS = "成功"
    FAILED = "失败"
    HUMAN = "待人工"


class TaskState(TypedDict, total=False):
    task_id: str                  # 任务唯一 ID
    product_code: str             # 商品编码
    target_shop: str              # 目标店铺标识
    product_material: dict        # ERP 检索到的商品素材
    sku_price_list: list          # SKU 与价格列表
    browser_env: Any              # 浏览器环境实例
    login_status: bool            # 登录状态
    captcha_type: str             # 验证码类型：none/slide/sms
    shelf_result: dict            # 上架结果
    retry_count: int              # 当前重试次数
    error_msg: str                # 错误信息
    status: str                   # 任务状态（见 TaskStatus）
    platform_item_id: str         # 平台返回商品 ID
    node_trace: list              # 节点执行轨迹（节点名/状态/时间戳）
    captcha_fail_count: int       # 本次任务验证码失败累计
    login_fail_count: int         # 本次任务登录失败累计
    risk_triggered: bool          # 是否已触发风控熔断
