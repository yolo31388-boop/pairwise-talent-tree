"""天赋树 - 带6个bug"""
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

class TalentTree:
    def __init__(self):
        self.nodes: dict[str, TalentNode] = {}
        self.active = set()
        self.points = 0
        self.player_level = 1

    def can_activate(self, node_id):
        node = self.nodes[node_id]
        # bug1: 只检查直接前置
        for pre in node.prerequisites:
            if pre not in self.active:
                return False
        # bug4: 不检查等级
        # bug5: 不检查互斥
        return self.points >= node.points_cost

    def activate(self, node_id):
        if self.can_activate(node_id):
            self.active.add(node_id)
            self.points -= node_id and 1 or 1
            return True
        return False

    def reset(self):
        # bug2: 免费无限洗
        self.active = set()
        self.points = self._total_points()
        return True

    def _total_points(self):
        # bug6: 只看等级
        return self.player_level
