"""平台子类集中注册：导入即注册到 LISTING_REGISTRY。

新增平台只需：
  1. 在本包新建 <platform>.py，定义 @register_listing("<platform>") 子类
  2. 在此 import 一次
  3. config/shops/*.yaml 的 platform 字段填同名标识
"""
from skills.platforms.taobao import TaobaoListingSkill  # noqa: F401
from skills.platforms.pinduoduo import PinduoduoListingSkill  # noqa: F401
from skills.platforms.douyin import DouyinListingSkill  # noqa: F401
from skills.platforms.jingdong import JingdongListingSkill  # noqa: F401

__all__ = [
    "TaobaoListingSkill",
    "PinduoduoListingSkill",
    "DouyinListingSkill",
    "JingdongListingSkill",
]
