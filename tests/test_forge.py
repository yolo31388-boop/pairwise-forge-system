"""锻造系统修复验证：8个材料黑洞"""
import random
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.engine import ForgeSystem, Recipe, Material, WEAPON_STATS, ARMOR_STATS


def make_fs(**kwargs):
    fs = ForgeSystem(**kwargs)
    fs.recipes["sword"] = Recipe("sword", "铁剑", [{"id": "iron", "qty": 5, "tier": 2}], 0.7, "rare", "weapon")
    return fs


class TestMaterialTier:
    def test_quantity_and_tier_both_checked(self):
        fs = make_fs()
        fs.add_material("iron", 100, tier=1)   # 数量够但等级不够
        assert not fs.check_materials("sword")
        fs.add_material("iron", 100, tier=3)   # 等级补足
        assert fs.check_materials("sword")
        fs.player_materials["iron"] = 2        # 数量不够
        assert not fs.check_materials("sword")


class TestSuccessRate:
    def test_rate_matches_config(self):
        fs = make_fs(success_pity=10**9)
        fs.recipes["always"] = Recipe("always", "必成", [], 1.0, "rare")
        for _ in range(50):
            assert fs.forge("always") is not None  # 100%配置必须全成，不是硬编码30%
        fs.recipes["never"] = Recipe("never", "必败", [], 0.0, "rare")
        for _ in range(50):
            assert fs.forge("never") is None

    def test_seeded_rate_approximately_config(self):
        random.seed(42)
        fs = make_fs(success_pity=10**9)
        fs.recipes["r70"] = Recipe("r70", "七成", [], 0.7, "rare")
        ok = sum(1 for _ in range(2000) if fs.forge("r70") is not None)
        assert 0.62 < ok / 2000 < 0.78

    def test_success_pity_guarantees(self):
        fs = make_fs(success_pity=8)
        fs.recipes["never"] = Recipe("never", "必败", [], 0.0, "rare")
        results = [fs.forge("never") for _ in range(8)]
        assert results[-1] is not None  # 连续失败触发保底必成


class TestQualityPity:
    def test_normal_streak_bounded(self):
        random.seed(7)
        fs = make_fs(quality_pity=10)
        fs.recipes["always"] = Recipe("always", "必成", [], 1.0, "rare")
        qualities = [fs.forge("always")["quality"] for _ in range(100)]
        streak = 0
        for q in qualities:
            streak = streak + 1 if q == "normal" else 0
            assert streak < 10  # 连续普通不得超过保底计数
        assert any(q != "normal" for q in qualities)


class TestStatPool:
    def test_stats_filtered_by_item_type(self):
        random.seed(1)
        fs = make_fs()
        fs.recipes["w"] = Recipe("w", "刀", [], 1.0, "rare", "weapon")
        fs.recipes["a"] = Recipe("a", "甲", [], 1.0, "rare", "armor")
        for _ in range(30):
            w = fs.forge("w")
            assert set(w["stats"]) <= set(WEAPON_STATS)  # 武器不出防御属性
            a = fs.forge("a")
            assert set(a["stats"]) <= set(ARMOR_STATS)   # 防具不出攻击属性


class TestConsumeOnSuccess:
    def test_failure_does_not_consume(self):
        fs = make_fs(success_pity=10**9)
        fs.recipes["never"] = Recipe("never", "必败", [{"id": "iron", "qty": 5, "tier": 2}], 0.0, "rare")
        fs.add_material("iron", 50, tier=3)
        for _ in range(10):
            assert fs.forge("never") is None
        assert fs.player_materials["iron"] == 50  # 失败不扣材料

    def test_success_consumes_once(self):
        fs = make_fs()
        fs.recipes["always"] = Recipe("always", "必成", [{"id": "iron", "qty": 5, "tier": 2}], 1.0, "rare")
        fs.add_material("iron", 50, tier=3)
        assert fs.forge("always") is not None
        assert fs.player_materials["iron"] == 45


class TestCancelRefund:
    def test_cancel_refunds_all(self):
        fs = make_fs()
        fs.add_material("iron", 50, tier=3)
        sid = fs.begin_forge("sword")
        assert fs.player_materials["iron"] == 45  # 进行中材料被预留
        assert fs.cancel_forge(sid)
        assert fs.player_materials["iron"] == 50  # 取消全额返还
        assert sum(fs.material_stacks["iron"]) == 50

    def test_failed_complete_refunds(self):
        fs = make_fs(success_pity=10**9)
        fs.recipes["never"] = Recipe("never", "必败", [{"id": "iron", "qty": 5, "tier": 2}], 0.0, "rare")
        fs.add_material("iron", 50, tier=3)
        sid = fs.begin_forge("never")
        assert fs.complete_forge(sid) is None
        assert fs.player_materials["iron"] == 50


class TestBatchForge:
    def test_batch_with_progress(self):
        fs = make_fs()
        fs.recipes["always"] = Recipe("always", "必成", [{"id": "iron", "qty": 1, "tier": 0}], 1.0, "rare")
        fs.add_material("iron", 20, tier=3)
        progress = []
        result = fs.forge_batch("always", 10, forger_id="smith1",
                                on_progress=lambda done, total: progress.append((done, total)))
        assert result["total"] == 10 and result["succeeded"] == 10
        assert len(result["items"]) == 10
        assert progress == [(i, 10) for i in range(1, 11)]  # 每步都有进度
        assert fs.player_materials["iron"] == 10


class TestTraceability:
    def test_forger_and_timestamp_recorded(self):
        fs = make_fs()
        fs.recipes["always"] = Recipe("always", "必成", [], 1.0, "rare")
        item = fs.forge("always", forger_id="player_777")
        assert item["forger"] == "player_777"
        assert item["forged_at"] > 0
        assert fs.get_forger(item["id"]) == "player_777"
        assert fs.get_forger(999999) == "unknown"


class TestStackLimit:
    def test_configurable_limit_and_cross_stack_consume(self):
        fs = ForgeSystem(stack_limit=99)
        fs.recipes["big"] = Recipe("big", "大剑", [{"id": "iron", "qty": 100, "tier": 1}], 1.0, "rare")
        fs.add_material("iron", 250, tier=3)
        assert fs.material_stacks["iron"] == [99, 99, 52]  # 自动分堆
        assert fs.check_materials("big")                    # 跨堆合计满足100
        item = fs.forge("big")
        assert item is not None
        assert fs.player_materials["iron"] == 150           # 跨堆扣除100
        assert sum(fs.material_stacks["iron"]) == 150
        fs2 = ForgeSystem(stack_limit=200)                  # 上限可配置
        fs2.add_material("iron", 250, tier=1)
        assert fs2.material_stacks["iron"] == [200, 50]
