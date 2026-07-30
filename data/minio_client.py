"""MinIO 对象存储封装：商品素材上传与预签名下载。"""
from __future__ import annotations

from datetime import timedelta

from minio import Minio

from config.settings import get_config


class MinIO:
    bucket = "ec-material"

    def __init__(self, cfg=None):
        cfg = cfg or get_config()
        self.cli = Minio(
            cfg.minio_endpoint,
            access_key=cfg.minio_access,
            secret_key=cfg.minio_secret,
            secure=cfg.minio_secure,
        )
        if not self.cli.bucket_exists(self.bucket):
            self.cli.make_bucket(self.bucket)

    def list_buckets(self):
        """委托到底层 SDK 客户端，供健康检查探测连通性。"""
        return self.cli.list_buckets()

    def put(self, object_name: str, file_path: str) -> str:
        self.cli.fput_object(self.bucket, object_name, file_path)
        return f"{self.bucket}/{object_name}"

    def presign(self, object_name: str, expires: int = 3600) -> str:
        return self.cli.presigned_get_object(
            self.bucket, object_name, expires=timedelta(seconds=expires)
        )


# 单例工厂：避免每次调用重复建桶检查
_client: MinIO | None = None


def get_minio_client() -> MinIO:
    global _client
    if _client is None:
        _client = MinIO()
    return _client
