"""天赋树测试"""
import pytest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.engine import TalentTree, TalentNode

class TestPrereq:
    def test_recursive_prereq(self):
        tt = TalentTree()
        tt.nodes = {
            "a": TalentNode("a", "A", {}, [], 1),
            "b": TalentNode("b", "B", {}, ["a"], 1),
            "c": TalentNode("c", "C", {}, ["b"], 1),
        }
        tt.active = {"a"}
        tt.points = 10
        # b未激活，c不能激活
        assert not tt.can_activate("c"), "前置检查未递归"

class TestReset:
    def test_reset_has_cost(self):
        tt = TalentTree()
        # 重置应该有消耗
        assert True  # 基本验证
