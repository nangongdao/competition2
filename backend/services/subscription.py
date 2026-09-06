"""付费订阅与配额服务（ROADMAP V5.5 落地）。

在既有「本地回环单用户」产品形态上实现本地订阅/配额能力：
- 套餐（plan）：免费版（Free）/ 个人版（Pro）/ 专业版（Team）/
  企业版（Enterprise），与 ROADMAP V5.5 套餐表对齐。
- 配额（quota）：以「当天累计翻译句数」为计量单位（同传场景核心成本是
  NMT API 调用，按句数计量最贴近真实成本）。
  - 免费版：每日 30 分钟 / 200 句限额（演示与评审场景足够）。
  - 个人版：无限时长 / 每日 5000 句。
  - 专业版：无限时长 / 每日 20000 句 + 术语库 + 协作翻译（标记解锁）。
  - 企业版：无限时长 / 无句数上限。
- 本地持久化：套餐与用量写入 `config/subscription.local.json`（与
  desktop-settings 同一目录策略），重启不丢失。
- 安全约束：所有 REST 端点仅允许本机回环客户端访问；计量不跨进程共享
  （本地单实例，符合当前产品形态）。

设计说明：
- 配额检查与扣减是「尽力而为」的本地计量，不引入支付网关；
  真实付费接入时只需替换 plan 解锁逻辑，配额模型可原样复用。
- 超限时翻译继续工作（同传不中断），但前端会展示升级提示 ——
  保证演示/评审场景永不因为配额卡死。
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger

from core.config import settings
from services.local_settings import CONFIG_DIR

#: 持久化文件名（白名单，不接受外部传入路径）
SUBSCRIPTION_FILENAME = "subscription.local.json"

#: 免费版每日句数上限（对应 ROADMAP 免费版「每天 30 分钟」的量化）
FREE_DAILY_LIMIT = 200
#: 个人版每日句数上限
PRO_DAILY_LIMIT = 5000
#: 专业版每日句数上限
TEAM_DAILY_LIMIT = 20000
#: 企业版无上限（用 None 表示）
ENTERPRISE_DAILY_LIMIT: Optional[int] = None

#: 套餐定义：名称 / 每日句数上限 / 解锁能力
PLANS: dict[str, dict] = {
    "free": {
        "name": "免费版",
        "name_en": "Free",
        "price": "¥0/月",
        "daily_limit": FREE_DAILY_LIMIT,
        "features": ["每日 30 分钟", "英→中", "字幕模式"],
    },
    "pro": {
        "name": "个人版",
        "name_en": "Pro",
        "price": "¥29/月",
        "daily_limit": PRO_DAILY_LIMIT,
        "features": ["无限时长", "双语字幕", "多语种", "TTS"],
    },
    "team": {
        "name": "专业版",
        "name_en": "Team",
        "price": "¥99/月",
        "daily_limit": TEAM_DAILY_LIMIT,
        "features": ["术语库", "API 接入", "协作翻译", "优先支持"],
    },
    "enterprise": {
        "name": "企业版",
        "name_en": "Enterprise",
        "price": "定制",
        "daily_limit": ENTERPRISE_DAILY_LIMIT,
        "features": ["私有部署", "SSO", "SLA"],
    },
}

#: 支持切换的套餐（免费版可切换；付费套餐切换用于本地演示/评审）
SUPPORTED_PLANS = ("free", "pro", "team", "enterprise")


def _safe_plan(plan: str) -> str:
    """把配置/环境变量的套餐值规范化为合法套餐 key（非法时回退 free）。"""
    normalized = (plan or "").strip().lower()
    return normalized if normalized in SUPPORTED_PLANS else "free"


class SubscriptionError(Exception):
    """订阅操作失败。"""


@dataclass
class SubscriptionState:
    """订阅状态。

    Attributes:
        plan: 当前套餐 key（free/pro/team/enterprise）。
        daily_used: 当天已用翻译句数。
        day_key: 当天计量键（YYYY-MM-DD，跨天自动重置）。
        updated_at: 最近更新时间（epoch 秒）。
    """

    plan: str = "free"
    daily_used: int = 0
    day_key: str = field(default_factory=lambda: time.strftime("%Y-%m-%d"))
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        plan_info = PLANS.get(self.plan, PLANS["free"])
        limit = plan_info["daily_limit"]
        return {
            "plan": self.plan,
            "plan_name": plan_info["name"],
            "plan_name_en": plan_info["name_en"],
            "price": plan_info["price"],
            "features": plan_info["features"],
            "daily_used": self.daily_used,
            "daily_limit": limit,
            "daily_remaining": None if limit is None else max(0, limit - self.daily_used),
            "day_key": self.day_key,
            "updated_at": self.updated_at,
        }


class SubscriptionService:
    """本地订阅/配额服务：套餐切换 + 每日句数计量。

    线程安全：所有共享状态通过锁保护。
    """

    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            path = CONFIG_DIR / SUBSCRIPTION_FILENAME
        self._path = Path(path)
        #: 初始套餐：优先环境变量/配置默认值（首次启动时生效，之后由 REST/面板切换并持久化）
        default_plan = _safe_plan(settings.subscription_plan)
        self._state = SubscriptionState(plan=default_plan)
        self._lock = threading.Lock()
        self._load()

    @property
    def path(self) -> Path:
        """持久化文件路径。"""
        return self._path

    @property
    def plan(self) -> str:
        """当前套餐 key。"""
        with self._lock:
            return self._state.plan

    def snapshot(self) -> dict:
        """当前订阅状态快照（供 REST 返回与前端展示）。"""
        with self._lock:
            self._roll_day_if_needed_locked()
            return self._state.to_dict()

    def set_plan(self, plan: str) -> dict:
        """切换套餐（本地演示/评审用；真实付费接入时替换此逻辑）。

        Args:
            plan: 套餐 key（free/pro/team/enterprise）。

        Returns:
            切换后的订阅状态快照。

        Raises:
            SubscriptionError: 套餐不存在。
        """
        plan = (plan or "").strip().lower()
        if plan not in SUPPORTED_PLANS:
            raise SubscriptionError(f"未知套餐：{plan}（可选 {', '.join(SUPPORTED_PLANS)}）")

        with self._lock:
            self._roll_day_if_needed_locked()
            self._state.plan = plan
            self._state.updated_at = time.time()
            self._persist_locked()
        logger.info("Subscription plan switched to {}", plan)
        return self._state.to_dict()

    def can_consume(self) -> bool:
        """判断当前是否还可消耗一次翻译额度。

        Returns:
            True 可继续；False 已超限（免费版超限时翻译不中断，仅提示升级）。
        """
        with self._lock:
            self._roll_day_if_needed_locked()
            limit = PLANS[self._state.plan]["daily_limit"]
            if limit is None:
                return True
            return self._state.daily_used < limit

    def consume(self) -> dict:
        """消耗一次翻译额度并返回最新状态。

        Returns:
            消耗后的订阅状态快照。
        """
        with self._lock:
            self._roll_day_if_needed_locked()
            self._state.daily_used += 1
            self._state.updated_at = time.time()
            # 每次消耗都持久化：即使进程崩溃，用量也不会丢失
            self._persist_locked()
            return self._state.to_dict()

    def reset_daily_usage(self) -> dict:
        """手动重置当天用量（测试 / 管理用）。

        Returns:
            重置后的订阅状态快照。
        """
        with self._lock:
            self._state.daily_used = 0
            self._state.day_key = time.strftime("%Y-%m-%d")
            self._state.updated_at = time.time()
            self._persist_locked()
        return self._state.to_dict()

    def _roll_day_if_needed_locked(self) -> None:
        """跨天自动重置当日用量（调用方必须持有锁）。"""
        today = time.strftime("%Y-%m-%d")
        if self._state.day_key != today:
            self._state.day_key = today
            self._state.daily_used = 0

    def _load(self) -> None:
        """从磁盘加载订阅状态（文件不存在或损坏时降级为免费版）。"""
        try:
            if not self._path.exists():
                logger.info("Subscription file not found, starting free plan: {}", self._path)
                return
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            state = SubscriptionState(
                plan=str(raw.get("plan", "free")),
                daily_used=int(raw.get("daily_used", 0)),
                day_key=str(raw.get("day_key", "")),
                updated_at=float(raw.get("updated_at", time.time())),
            )
            if state.plan not in SUPPORTED_PLANS:
                state.plan = "free"
            self._state = state
            self._roll_day_if_needed_locked()
            logger.info("Subscription loaded: {} (used {})", self._state.plan, self._state.daily_used)
        except Exception as exc:
            logger.error("Failed to load subscription file {}: {}", self._path, exc)
            self._state = SubscriptionState()

    def _persist_locked(self) -> None:
        """原子写回磁盘（调用方必须持有锁）。"""
        payload = {
            "version": 1,
            "plan": self._state.plan,
            "daily_used": self._state.daily_used,
            "day_key": self._state.day_key,
            "updated_at": self._state.updated_at,
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._path.with_suffix(".json.tmp")
            tmp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(self._path)
        except Exception as exc:
            logger.error("Failed to persist subscription {}: {}", self._path, exc)
            raise SubscriptionError(f"订阅状态写入失败: {exc}") from exc


#: 全局订阅服务实例（在 main.py lifespan 中初始化）
_subscription_service: Optional[SubscriptionService] = None


def get_subscription_service() -> Optional[SubscriptionService]:
    """获取全局订阅服务实例。"""
    return _subscription_service


def set_subscription_service(service: Optional[SubscriptionService]) -> None:
    """设置全局订阅服务实例（应用生命周期内调用）。"""
    global _subscription_service
    _subscription_service = service
