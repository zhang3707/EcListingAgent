"""SQLAlchemy ORM 模型：任务、店铺、运行日志。"""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, JSON, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Task(Base):
    __tablename__ = "tasks"

    task_id = Column(String, primary_key=True)
    product_code = Column(String, index=True)
    target_shop = Column(String, index=True)
    status = Column(String, default="待执行")           # 见 agent.state.TaskStatus
    platform_item_id = Column(String, default="")
    sku_count = Column(Integer, default=0)
    error_msg = Column(Text, default="")
    operator = Column(String, default="")
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    extra = Column(JSON, default=dict)


class Shop(Base):
    __tablename__ = "shops"

    shop_id = Column(String, primary_key=True)
    shop_name = Column(String)
    platform = Column(String)
    base_url = Column(String)
    config_path = Column(String)
    proxy_server = Column(String, default="")
    login_count_today = Column(Integer, default=0)
    last_login_at = Column(DateTime, nullable=True)
    risk_status = Column(String, default="normal")      # normal / limited


class RunLog(Base):
    __tablename__ = "run_logs"

    id = Column(String, primary_key=True)               # {task_id}-{i}
    task_id = Column(String, index=True)
    node = Column(String)
    status = Column(String)
    ts = Column(DateTime, default=datetime.utcnow)
    detail = Column(Text, default="")
