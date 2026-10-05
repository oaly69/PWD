"""运行时配置。

容器只需要极少的环境变量，其余参数全部在首次启动的安装页面中设置并存入数据库。

支持的环境变量（全部可选）：
- PWD_DATA_DIR       数据目录，默认 /data（本地开发默认 ./data）
- PWD_PORT           监听端口，默认 8080
- PWD_INSTALL_TOKEN  若设置，则安装页面必须输入该令牌才能完成安装（公网部署建议设置）
"""
from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path

VERSION = os.environ.get("PWD_VERSION", "0.6.0")


def _default_data_dir() -> Path:
    if Path("/.dockerenv").exists():
        return Path("/data")
    return Path(__file__).resolve().parent.parent.parent / "data"


class Settings:
    def __init__(self) -> None:
        self.data_dir = Path(os.environ.get("PWD_DATA_DIR") or _default_data_dir()).resolve()
        self.port = int(os.environ.get("PWD_PORT", "8080"))
        self.install_token = os.environ.get("PWD_INSTALL_TOKEN", "").strip()
        self.static_dir = Path(
            os.environ.get("PWD_STATIC_DIR")
            or Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
        )

    @property
    def db_path(self) -> Path:
        return self.data_dir / "pwd.db"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def secret_file(self) -> Path:
        return self.data_dir / ".secret_key"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.media_dir.mkdir(parents=True, exist_ok=True)

    @property
    def secret_key(self) -> str:
        """会话签名密钥：首次启动自动生成并持久化在数据目录中。"""
        return _load_secret(self.secret_file)


@lru_cache
def _load_secret(path: Path) -> str:
    if path.exists():
        value = path.read_text().strip()
        if value:
            return value
    path.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_urlsafe(48)
    path.write_text(value)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return value


settings = Settings()
