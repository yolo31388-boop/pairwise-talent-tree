"""天赋树系统测试：6 个灾难的回归验证。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from talent.tree import TalentTree, TalentNode, TalentError


def _chain_tree():
    """a -> b -> c 的三级链。"""
    tt = TalentTree()
    tt.nodes = {
        "a": TalentNode("a", "A", {"atk": 1}, [], 1),
        "b": TalentNode("b", "B", {"atk": 2}, ["a"], 2),
        "c": TalentNode("c", "C", {"atk": 4}, ["b"], 5),
    }
    tt.active = {"a"}
    tt.points = 10
    tt.player_level = 10
    return tt


class TestPrereq:
    def test_recursive_prereq_chain(self):
        """灾难1：前置必须递归验证整条路径。"""
        tt = _chain_tree()
        # 中间节点 b 未激活，终极节点 c 不能点
        assert not tt.can_activate("c"), "前置检查未递归整条路径"
        assert tt.can_activate("b")
        assert tt.activate("b")
        assert tt.can_activate("c")
        assert tt.activate("c")


class TestLevelRequirement:
    def test_level_required_blocks_activation(self):
        """灾难4：节点有最低角色等级要求。"""
        tt = _chain_tree()
        tt.player_level = 1
        assert not tt.can_activate("b"), "1 级不应能点 2 级天赋"
        assert not tt.activate("b")
        tt.player_level = 2
        assert tt.can_activate("b")
        assert tt.activate("b")


class TestMutualExclusion:
    def test_exclusive_group_single_active(self):
        """灾难5：互斥组只能激活一个，点新的自动取消旧的。"""
        tt = TalentTree()
        tt.nodes = {
            "u1": TalentNode("u1", "终极·火", {"fire": 10}, [], 1, "ult"),
            "u2": TalentNode("u2", "终极·冰", {"ice": 10}, [], 1, "ult"),
        }
        tt.points = 10
        assert tt.activate("u1")
        assert "u1" in tt.active
        assert tt.activate("u2")
        assert "u2" in tt.active and "u1" not in tt.active, "点互斥天赋应自动取消旧的"
        assert tt.points == 9, "自动取消应返还被取消节点的点"


class TestResetCost:
    def test_reset_cost_or_cooldown(self):
        """灾难2：洗点不能无限免费，需道具或冷却。"""
        tt = TalentTree(reset_cooldown=100)
        tt.nodes = {"a": TalentNode("a", "A", {}, [], 1)}
        tt.grant_points(5, "level")
        assert tt.activate("a")
        # 首次免费
        assert tt.reset(now=1000)
        assert tt.active == set() and tt.points == 5
        # 冷却中：无道具不能洗
        assert not tt.can_reset(now=1050)
        assert not tt.reset(now=1050)
        # 有洗点道具：消耗道具无视冷却
        tt.activate("a")
        tt.add_reset_item(1)
        assert tt.reset(now=1050)
        assert tt.reset_items == 0
        assert tt.points == 5
        # 冷却过后可再次免费洗
        assert tt.can_reset(now=1100)


class TestDataDriven:
    def test_effects_from_config(self):
        """灾难3：天赋效果数据驱动，新增天赋不改核心代码。"""
        tt = TalentTree()
        tt.load_config([
            {"nid": "str1", "name": "力量I", "effect": {"atk": 3},
             "prerequisites": [], "level_required": 1},
            {"nid": "str2", "name": "力量II", "effect": {"atk": 7, "crit": 5},
             "prerequisites": ["str1"], "level_required": 1},
        ])
        tt.points = 10
        assert tt.activate("str1")
        assert tt.activate("str2")
        assert tt.effects() == {"atk": 10, "crit": 5}
        stats = tt.apply_to({"hp": 100})
        assert stats["atk"] == 10 and stats["hp"] == 100

    def test_load_config_from_json_file(self, tmp_path):
        import json
        path = tmp_path / "talents.json"
        path.write_text(json.dumps({"nodes": [
            {"nid": "x", "name": "X", "effect": {"def": 2}},
        ]}), encoding="utf-8")
        tt = TalentTree()
        tt.load_config(path)
        assert "x" in tt.nodes and tt.nodes["x"].effect == {"def": 2}


class TestPointSources:
    def test_multiple_point_sources(self):
        """灾难6：天赋点来源多元化。"""
        tt = TalentTree()
        tt.grant_points(3, "level")
        tt.grant_points(1, "achievement")
        tt.grant_points(2, "quest")
        tt.grant_points(1, "item")
        assert tt.points == 7
        assert tt.points_by_source() == {
            "level": 3, "achievement": 1, "quest": 2, "item": 1,
        }
        assert tt.total_granted_points() == 7
        for bad in ("cheat", "hacker"):
            try:
                tt.grant_points(1, bad)
                assert False, "非法来源应报错"
            except TalentError:
                pass
        # 洗点后各来源的总点数被完整返还
        tt.nodes = {"a": TalentNode("a", "A", {}, [], 1)}
        tt.activate("a")
        assert tt.points == 6
        tt.reset(now=0)
        assert tt.points == 7
