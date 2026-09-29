"""装备锻造系统"""
from dataclasses import dataclass, field
import random
import time

# 附加属性池按装备类型划分：武器只出攻击类，防具只出防御类
WEAPON_STATS = ("attack", "crit", "penetration", "attack_speed")
ARMOR_STATS = ("defense", "hp", "dodge", "resistance")


@dataclass
class Material:
    mid: str
    name: str
    tier: int
    quantity: int


@dataclass
class Recipe:
    rid: str
    name: str
    materials: list
    success_rate: float
    output_quality: str
    item_type: str = "weapon"  # weapon / armor，决定附加属性池


class ForgeSystem:
    def __init__(self, stack_limit=99, quality_pity=10, success_pity=10):
        self.recipes: dict[str, Recipe] = {}
        self.player_materials: dict[str, int] = {}   # 聚合数量视图（跨堆合计）
        self.material_tiers: dict[str, int] = {}     # mid -> 材料等级
        self.material_stacks: dict[str, list] = {}   # mid -> [每堆数量, ...]
        self.stack_limit = stack_limit               # 堆叠上限可配置
        self.quality_pity = quality_pity             # 连续N次普通后必出更高品质
        self.success_pity = success_pity             # 连续N次失败后必成功
        self.forged_items = []
        self.pity_counter = 0        # 连续普通品质计数
        self.fail_counter = 0        # 连续失败计数
        self._item_seq = 0
        self._sessions = {}
        self._session_seq = 0

    # ---------- 材料管理：堆叠上限可配置 ----------
    def add_material(self, mid, qty, tier=0, name=""):
        """入库材料，按 stack_limit 自动分堆。"""
        self.material_tiers[mid] = max(tier, self.material_tiers.get(mid, 0))
        stacks = self.material_stacks.setdefault(mid, [])
        remaining = qty
        while remaining > 0:
            if stacks and stacks[-1] < self.stack_limit:
                take = min(self.stack_limit - stacks[-1], remaining)
                stacks[-1] += take
            else:
                take = min(self.stack_limit, remaining)
                stacks.append(take)
            remaining -= take
        self.player_materials[mid] = self.player_materials.get(mid, 0) + qty

    def _consume_materials(self, materials):
        """跨堆扣除材料，返回实际扣除明细 [(mid, qty)]。"""
        consumed = []
        for mat in materials:
            mid, need = mat["id"], mat["qty"]
            stacks = self.material_stacks.get(mid, [])
            left = need
            while left > 0 and stacks:
                take = min(stacks[0], left)
                stacks[0] -= take
                left -= take
                if stacks[0] == 0:
                    stacks.pop(0)
            # 堆记录不足时（如直接赋值 player_materials），从聚合视图扣差额
            self.player_materials[mid] = self.player_materials.get(mid, 0) - (need - left)
            consumed.append((mid, need - left))
        return consumed

    def _refund_materials(self, consumed):
        for mid, qty in consumed:
            if qty > 0:
                self.add_material(mid, qty, tier=self.material_tiers.get(mid, 0))

    # ---------- 材料检查：数量 + 等级 ----------
    def check_materials(self, recipe_id):
        recipe = self.recipes[recipe_id]
        for mat in recipe.materials:
            mid = mat["id"]
            if self.player_materials.get(mid, 0) < mat["qty"]:
                return False
            if self.material_tiers.get(mid, 0) < mat.get("tier", 0):
                return False
        return True

    # ---------- 附加属性：按装备类型过滤池 ----------
    def _roll_stats(self, recipe):
        if recipe.item_type == "weapon":
            pool = WEAPON_STATS
        elif recipe.item_type == "armor":
            pool = ARMOR_STATS
        else:
            pool = WEAPON_STATS + ARMOR_STATS
        count = random.randint(1, min(3, len(pool)))
        return {stat: random.randint(1, 100) for stat in random.sample(pool, count)}

    # ---------- 品质：随机 + 保底计数 ----------
    def _roll_quality(self, recipe):
        roll = random.random()
        if roll < 0.03:
            quality = "legendary"
        elif roll < 0.10:
            quality = "epic"
        elif roll < 0.30:
            quality = "rare"
        else:
            quality = "normal"
        if quality == "normal":
            self.pity_counter += 1
            if self.pity_counter >= self.quality_pity:
                self.pity_counter = 0
                return recipe.output_quality  # 保底：必出更高品质
            return "normal"
        self.pity_counter = 0
        return quality

    # ---------- 成功率：以配置为准 + 失败保底 ----------
    def _roll_success(self, recipe):
        if random.random() < recipe.success_rate:
            self.fail_counter = 0
            return True
        self.fail_counter += 1
        if self.fail_counter >= self.success_pity:
            self.fail_counter = 0
            return True
        return False

    def _make_item(self, recipe, forger_id):
        self._item_seq += 1
        item = {
            "id": self._item_seq,
            "name": recipe.name,
            "quality": self._roll_quality(recipe),
            "stats": self._roll_stats(recipe),
            "forger": forger_id if forger_id is not None else "unknown",
            "forged_at": time.time(),  # 可溯源：锻造者 + 时间
        }
        self.forged_items.append(item)
        return item

    # ---------- 锻造：成功时才扣材料 ----------
    def forge(self, recipe_id, forger_id=None):
        recipe = self.recipes[recipe_id]
        if not self.check_materials(recipe_id):
            return None
        if not self._roll_success(recipe):
            return None  # 失败不扣材料
        self._consume_materials(recipe.materials)
        return self._make_item(recipe, forger_id)

    # ---------- 分段锻造：中途取消全额返还 ----------
    def begin_forge(self, recipe_id, forger_id=None):
        """开始锻造并预留材料，返回会话ID，可 complete_forge 或 cancel_forge。"""
        if not self.check_materials(recipe_id):
            return None
        consumed = self._consume_materials(self.recipes[recipe_id].materials)
        self._session_seq += 1
        self._sessions[self._session_seq] = {
            "recipe_id": recipe_id,
            "forger_id": forger_id,
            "reserved": consumed,
            "done": False,
        }
        return self._session_seq

    def complete_forge(self, session_id):
        """完成锻造：成功消耗预留材料，失败自动返还。"""
        session = self._sessions.get(session_id)
        if not session or session["done"]:
            return None
        session["done"] = True
        recipe = self.recipes[session["recipe_id"]]
        if not self._roll_success(recipe):
            self._refund_materials(session["reserved"])
            return None
        return self._make_item(recipe, session["forger_id"])

    def cancel_forge(self, session_id):
        """取消锻造，预留材料全额返还。"""
        session = self._sessions.get(session_id)
        if not session or session["done"]:
            return False
        session["done"] = True
        self._refund_materials(session["reserved"])
        return True

    # ---------- 批量锻造：带进度回调 ----------
    def forge_batch(self, recipe_id, count, forger_id=None, on_progress=None):
        """连续锻造 count 次，on_progress(done, total) 汇报进度。"""
        items = []
        attempts = 0
        for i in range(count):
            item = self.forge(recipe_id, forger_id=forger_id)
            attempts += 1
            if item is not None:
                items.append(item)
            if on_progress:
                on_progress(i + 1, count)
        return {
            "total": count,
            "attempts": attempts,
            "succeeded": len(items),
            "items": items,
        }

    # ---------- 溯源 ----------
    def get_forger(self, item_id):
        for item in self.forged_items:
            if item["id"] == item_id:
                return item["forger"]
        return "unknown"
