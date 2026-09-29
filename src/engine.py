"""天赋树核心 - 数据驱动，修复6个加点灾难"""
import time
from dataclasses import dataclass, field


@dataclass
class TalentNode:
    nid: str
    name: str
    effect: dict
    prerequisites: list
    level_required: int
    mutually_exclusive: str = None
    points_cost: int = 1


# ---------------------------------------------------------------------------
# 效果处理器注册表（修复 bug3：效果数据驱动，新增天赋/效果类型不改核心代码）
# effect 形如 {"type": "stat_boost", "stat": "strength", "value": 5}
# 新效果类型只需 register_effect_handler("xxx", handler)，无需改动本文件逻辑。
# ---------------------------------------------------------------------------
EFFECT_HANDLERS = {}


def register_effect_handler(effect_type, handler):
    """handler(accumulator: dict, effect: dict) -> None"""
    EFFECT_HANDLERS[effect_type] = handler


def _stat_boost_handler(acc, effect):
    stat = effect.get("stat")
    acc[stat] = acc.get(stat, 0) + effect.get("value", 0)


def _multiply_stat_handler(acc, effect):
    stat = effect.get("stat")
    acc[stat] = acc.get(stat, 0) * effect.get("factor", 1)


register_effect_handler("stat_boost", _stat_boost_handler)
register_effect_handler("multiply_stat", _multiply_stat_handler)


class TalentTree:
    # 洗点冷却（秒），可按实例覆盖
    RESET_COOLDOWN = 60.0
    # 合法的天赋点来源（修复 bug6：来源多元化）
    POINT_SOURCES = ("level", "achievement", "quest", "item")

    def __init__(self, clock=time.monotonic):
        self.nodes: dict[str, TalentNode] = {}
        self.active = set()
        self.points = 0
        self.player_level = 1
        # 洗点消耗品数量（修复 bug2：重置消耗道具 + 冷却）
        self.reset_tokens = 0
        self.reset_cooldown = self.RESET_COOLDOWN
        self._last_reset_at = None
        self._clock = clock
        # 各来源累计获得的天赋点（level 来源由 player_level 派生，不计入此表）
        self.points_by_source = {"achievement": 0, "quest": 0, "item": 0}

    # ------------------------------------------------------------------
    # 数据驱动加载：新增天赋只加配置，不改代码
    # ------------------------------------------------------------------
    def add_node(self, data: dict):
        self.nodes[data["nid"]] = TalentNode(**data)

    @classmethod
    def from_config(cls, nodes_config, **kwargs):
        tree = cls(**kwargs)
        for data in nodes_config:
            tree.add_node(data)
        return tree

    # ------------------------------------------------------------------
    # bug1 修复：递归验证整条前置链，链上所有节点都激活才算满足
    # ------------------------------------------------------------------
    def _chain_active(self, nid, seen):
        if nid in seen:
            return True  # 循环保护
        seen.add(nid)
        if nid not in self.active:
            return False
        node = self.nodes.get(nid)
        if node is None:
            return False
        return all(self._chain_active(pre, seen) for pre in node.prerequisites)

    def can_activate(self, node_id):
        node = self.nodes.get(node_id)
        if node is None or node_id in self.active:
            return False
        # 递归前置检查
        for pre in node.prerequisites:
            if not self._chain_active(pre, set()):
                return False
        # bug4 修复：最低角色等级要求
        if self.player_level < node.level_required:
            return False
        # bug5：互斥不阻止加点，activate 时自动取消同组已激活节点
        return self.points >= node.points_cost

    def activate(self, node_id):
        if not self.can_activate(node_id):
            return False
        node = self.nodes[node_id]
        # bug5 修复：互斥组内只能激活一个，点新的自动取消旧的
        if node.mutually_exclusive:
            for other_id in list(self.active):
                other = self.nodes.get(other_id)
                if (
                    other is not None
                    and other_id != node_id
                    and other.mutually_exclusive == node.mutually_exclusive
                ):
                    self.active.discard(other_id)
        self.active.add(node_id)
        self.points -= node.points_cost
        return True

    # ------------------------------------------------------------------
    # bug2 修复：洗点需要消耗道具且受冷却限制，不能无限免费洗
    # ------------------------------------------------------------------
    def can_reset(self):
        if self.reset_tokens <= 0:
            return False
        if (
            self._last_reset_at is not None
            and self._clock() - self._last_reset_at < self.reset_cooldown
        ):
            return False
        return True

    def reset(self):
        if not self.can_reset():
            return False
        self.reset_tokens -= 1
        self._last_reset_at = self._clock()
        self.active = set()
        self.points = self._total_points()
        return True

    def grant_reset_token(self, count=1):
        self.reset_tokens += count

    # ------------------------------------------------------------------
    # bug6 修复：天赋点来源多元化（等级/成就/任务/特殊物品）
    # ------------------------------------------------------------------
    def grant_points(self, amount, source="item"):
        if source not in self.POINT_SOURCES:
            raise ValueError(f"未知天赋点来源: {source}")
        if source == "level":
            # 等级点数由 player_level 派生，不重复入账
            self.player_level += amount
        else:
            self.points_by_source[source] += amount
        self.points += amount

    def complete_achievement(self, achievement_id, points=1):
        self.grant_points(points, source="achievement")

    def complete_quest(self, quest_id, points=1):
        self.grant_points(points, source="quest")

    def use_point_item(self, item_id, points=1):
        self.grant_points(points, source="item")

    def _total_points(self):
        return self.player_level + sum(self.points_by_source.values())

    # ------------------------------------------------------------------
    # bug3 修复：效果按数据驱动聚合
    # ------------------------------------------------------------------
    def compute_effects(self):
        """聚合所有已激活节点的效果，返回累计结果字典。"""
        result = {}
        for nid in self.active:
            node = self.nodes.get(nid)
            if node is None:
                continue
            handler = EFFECT_HANDLERS.get(node.effect.get("type"))
            if handler is not None:
                handler(result, node.effect)
        return result
