"""数据库引擎、会话工厂、LangGraph Postgres checkpointer。"""
from __future__ import annotations

from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from config.settings import get_config

_engine = None
_SessionLocal = None
_checkpointer = None
_checkpointer_cm = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(get_config().pg_dsn, pool_pre_ping=True, future=True)
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal


@contextmanager
def session_scope() -> Session:
    """事务作用域：正常提交，异常回滚。"""
    s = get_session_factory()()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def _psycopg_dsn() -> str:
    """将 SQLAlchemy DSN 转为原生 psycopg 连接串。

    SQLAlchemy 形如 postgresql+psycopg://user:pwd@host:5432/db，
    原生 psycopg 不识别 +driver 后缀，需剥离为 postgresql://...
    """
    import re
    return re.sub(r"postgresql\+\w+://", "postgresql://", get_config().pg_dsn)


def get_checkpointer():
    """LangGraph Postgres 持久化，支持 interrupt 挂起恢复。

    兼容新旧导入路径（包名均为 langgraph-checkpoint-postgres）：
      - 新版（2.x+）: langgraph_postgres
      - 旧版（1.x）  : langgraph.checkpoint.postgres
    需安装：pip install langgraph-checkpoint-postgres

    单例：worker 长驻进程内只建一次连接，跨任务复用，避免每次任务新建连接。
    """
    global _checkpointer
    if _checkpointer is not None:
        return _checkpointer

    PostgresSaver = None
    for mod_path, attr in [
        ("langgraph_postgres", "PostgresSaver"),
        ("langgraph.checkpoint.postgres", "PostgresSaver"),
    ]:
        try:
            import importlib
            mod = importlib.import_module(mod_path)
            PostgresSaver = getattr(mod, attr)
            break
        except ImportError:
            continue
    if PostgresSaver is None:
        raise ImportError(
            "未安装 LangGraph Postgres checkpointer，请运行: pip install langgraph-checkpoint-postgres"
        )

    raw = PostgresSaver.from_conn_string(_psycopg_dsn())
    # from_conn_string 在 2.x+ 是 @classmethod @contextmanager，返回 _GeneratorContextManager；
    # 需 __enter__() 获取真实 PostgresSaver 实例。旧版直接返回 saver 实例（有 setup 方法）。
    # 持有 cm 引用（_checkpointer_cm）避免连接被 GC 关闭。
    if hasattr(raw, "setup"):
        _checkpointer = raw
    else:
        global _checkpointer_cm
        _checkpointer_cm = raw
        _checkpointer = raw.__enter__()
    if hasattr(_checkpointer, "setup"):
        _checkpointer.setup()
    return _checkpointer
