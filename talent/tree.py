"""数据驱动的天赋树系统。

修复的六个问题：
1. 前置检查沿 prerequisites 递归验证整条祖先路径；
2. 洗点需要消耗洗点道具或等待冷却，无法无限免费重置；
3. 节点与效果全部由配置数据描述，新增天赋只需加配置；
4. 节点带最低角色等级要求；
5. 互斥组内只能激活一个，激活新节点自动取消旧节点；
6. 天赋点来源多元化：等级 / 成就 / 任务 / 特殊物品。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional, Union

#: 合法的天赋点来源
POINT_SOURCES = ("level", "achievement", "quest", "item")

#: 默认洗点冷却（秒），避免无限免费洗点
DEFAULT_RESET_COOLDOWN = 24 * 60 * 60


class TalentError(ValueError):
    """天赋系统配置或操作错误。"""


@dataclass
class TalentNode:
    nid: str
    name: str
    effect: dict = field(default_factory=dict)
    prerequisites: list = field(default_factory=list)
    level_required: int = 1
    mutually_exclusive: Optional[str] = None
    points_cost: int = 1

    @classmethod
    def from_dict(cls, data: Mapping) -> "TalentNode":
        """从纯数据（如 JSON 配置）构造节点，新增天赋无需改核心代码。"""
        allowed = {
            "nid",
            "name",
            "effect",
            "prerequisites",
            "level_required",
            "mutually_exclusive",
            "points_cost",
        }
        unknown = set(data) - allowed
        if unknown:
            raise TalentError(f"未知天赋配置字段: {sorted(unknown)}")
        if "nid" not in data or "name" not in data:
            raise TalentError("天赋配置缺少 nid/name")
        return cls(
            nid=data["nid"],
            name=data["name"],
            effect=dict(data.get("effect", {})),
            prerequisites=list(data.get("prerequisites", [])),
            level_required=int(data.get("level_required", 1)),
            mutually_exclusive=data.get("mutually_exclusive"),
            points_cost=int(data.get("points_cost", 1)),
        )


class TalentTree:
    def __init__(self, reset_cooldown: float = DEFAULT_RESET_COOLDOWN):
        self.nodes: dict[str, TalentNode] = {}
        self.active: set[str] = set()
        self.points = 0
        self.player_level = 1

        # 洗点成本：道具优先，否则受冷却限制
        self.reset_cooldown = reset_cooldown
        self.reset_items = 0
        self._last_reset_at: Optional[float] = None

        # 各来源累计获得的天赋点
        self._granted = {source: 0 for source in POINT_SOURCES}

    # ------------------------------------------------------------------
    # 数据驱动配置
    # ------------------------------------------------------------------
    def load_config(
        self, config: Union[str, Path, Mapping, list]
    ) -> dict[str, TalentNode]:
        """加载天赋配置。

        支持三种形态：
        * JSON 文件路径；
        * ``{"nodes": [...]}`` 字典；
        * 节点字典组成的列表。
        所有效果都以 ``{属性: 增量}`` 的纯数据描述，核心代码不感知具体天赋。
        """
        if isinstance(config, (str, Path)):
            with open(config, encoding="utf-8") as handle:
                config = json.load(handle)
        if isinstance(config, Mapping) and "nodes" in config:
            config = config["nodes"]
        if not isinstance(config, (list, tuple)):
            raise TalentError("天赋配置必须是节点列表")
        for item in config:
            node = item if isinstance(item, TalentNode) else TalentNode.from_dict(item)
            self.nodes[node.nid] = node
        return self.nodes

    def add_node(self, node: Union[TalentNode, Mapping]) -> TalentNode:
        if not isinstance(node, TalentNode):
            node = TalentNode.from_dict(node)
        self.nodes[node.nid] = node
        return node

    # ------------------------------------------------------------------
    # 天赋点：等级 / 成就 / 任务 / 特殊物品
    # ------------------------------------------------------------------
    def grant_points(self, amount: int = 1, source: str = "level") -> int:
        if source not in POINT_SOURCES:
            raise TalentError(
                f"非法天赋点来源: {source!r}，合法值: {POINT_SOURCES}"
            )
        if amount <= 0:
            raise TalentError("天赋点数量必须为正整数")
        self._granted[source] += amount
        self.points += amount
        return self.points

    def add_reset_item(self, count: int = 1) -> int:
        if count <= 0:
            raise TalentError("洗点道具数量必须为正整数")
        self.reset_items += count
        return self.reset_items

    def total_granted_points(self) -> int:
        return sum(self._granted.values())

    def points_by_source(self) -> dict[str, int]:
        return dict(self._granted)

    def _total_points(self) -> int:
        # 兼容旧接口：历史累计获得的天赋点总数
        return self.total_granted_points()

    # ------------------------------------------------------------------
    # 前置路径 / 等级 / 点数检查
    # ------------------------------------------------------------------
    def ancestors(self, node_id: str) -> set[str]:
        """递归收集整条前置路径上的所有祖先节点（带环保护）。"""
        result: set[str] = set()
        stack = list(self.nodes[node_id].prerequisites)
        while stack:
            pre = stack.pop()
            if pre in result:
                continue
            result.add(pre)
            parent = self.nodes.get(pre)
            if parent is not None:
                stack.extend(parent.prerequisites)
        return result

    def can_activate(self, node_id: str) -> bool:
        node = self.nodes[node_id]
        if node_id in self.active:
            return False
        # 修复4：最低角色等级要求
        if self.player_level < node.level_required:
            return False
        # 修复1：整条前置路径上的每个节点都必须已激活
        if any(pre not in self.active for pre in self.ancestors(node_id)):
            return False
        # 互斥不阻塞激活：激活时自动取消同组的旧节点（见 activate）
        return self.points >= node.points_cost

    def activate(self, node_id: str) -> bool:
        if not self.can_activate(node_id):
            return False
        node = self.nodes[node_id]

        # 修复5：互斥组内只能有一个激活节点，点新节点自动取消旧节点
        refund = 0
        if node.mutually_exclusive is not None:
            for other_id in tuple(self.active):
                other = self.nodes.get(other_id)
                if (
                    other is not None
                    and other.mutually_exclusive == node.mutually_exclusive
                ):
                    self.active.discard(other_id)
                    refund += other.points_cost

        self.active.add(node_id)
        self.points -= node.points_cost
        self.points += refund  # 被自动取消的节点返还其消耗
        return True

    # ------------------------------------------------------------------
    # 数据驱动的效果聚合
    # ------------------------------------------------------------------
    def effects(self) -> dict:
        """聚合所有已激活节点的效果，效果完全来自节点配置数据。"""
        total: dict = {}
        for node_id in self.active:
            for key, value in self.nodes[node_id].effect.items():
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                total[key] = total.get(key, 0) + value
        return total

    def apply_to(self, stats: dict) -> dict:
        """把当前天赋效果叠加到属性字典上（通用入口，不硬编码任何天赋）。"""
        for key, value in self.effects().items():
            stats[key] = stats.get(key, 0) + value
        return stats

    # ------------------------------------------------------------------
    # 洗点：道具消耗或冷却
    # ------------------------------------------------------------------
    def can_reset(self, now: Optional[float] = None) -> bool:
        if self.reset_items > 0:
            return True
        if self._last_reset_at is None:
            return True
        current = time.monotonic() if now is None else now
        return current - self._last_reset_at >= self.reset_cooldown

    def reset(self, now: Optional[float] = None) -> bool:
        current = time.monotonic() if now is None else now
        if not self.can_reset(current):
            return False
        if self.reset_items > 0:
            # 修复2：消耗洗点道具（道具洗点不刷新免费冷却）
            self.reset_items -= 1
        else:
            self._last_reset_at = current
        self.active.clear()
        self.points = self.total_granted_points()
        return True
