"""操作日志。调用方负责 commit（与业务修改在同一事务中提交）。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from ..models import AuditLog, User

ACTION_LABEL = {
    "auth.login": "登录",
    "auth.login_failed": "登录失败",
    "auth.register": "注册",
    "auth.password": "修改密码",
    "auth.2fa_enable": "开启两步验证",
    "auth.2fa_disable": "关闭两步验证",
    "auth.oidc_login": "单点登录",
    "auth.oidc_link": "绑定单点登录",
    "user.create": "添加用户",
    "user.update": "修改用户",
    "user.delete": "删除用户",
    "group.create": "创建用户组",
    "group.update": "修改用户组",
    "group.delete": "删除用户组",
    "provider.create": "添加模型服务",
    "provider.update": "修改模型服务",
    "provider.delete": "删除模型服务",
    "settings.update": "修改系统设置",
    "system.backup": "下载备份",
    "system.storage_sync": "同步对象存储",
}


def client_ip(request: Request | None) -> str:
    if request is None:
        return ""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    return request.client.host if request.client else ""


def audit(
    db: Session,
    user: User | None,
    action: str,
    target: str = "",
    detail: str = "",
    request: Request | None = None,
    username: str = "",
) -> None:
    db.add(AuditLog(
        user_id=user.id if user else None,
        username=(user.username if user else username)[:64],
        action=action,
        target=target[:255],
        detail=detail[:2000],
        ip=client_ip(request),
    ))
