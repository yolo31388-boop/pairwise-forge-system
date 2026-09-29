"""装备锻造 - 带8个bug"""
from dataclasses import dataclass, field
import random

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

class ForgeSystem:
    def __init__(self):
        self.recipes: dict[str, Recipe] = {}
        self.player_materials: dict[str, int] = {}
        self.forged_items = []
        self.pity_counter = 0  # bug3: 无保底

    def check_materials(self, recipe_id):
        recipe = self.recipes[recipe_id]
        for mat in recipe.materials:
            # bug1: 只看数量不看等级
            if self.player_materials.get(mat["id"], 0) < mat["qty"]:
                return False
        return True

    def forge(self, recipe_id):
        recipe = self.recipes[recipe_id]
        if not self.check_materials(recipe_id):
            return None
        # bug5: 开始就扣材料
        for mat in recipe.materials:
            self.player_materials[mat["id"]] -= mat["qty"]
        # bug2: 硬编码30%
        if random.random() < 0.3:
            # bug4: 全局属性池
            item = {"name": recipe.name, "quality": "normal", "stats": {"attack": random.randint(1,100)}}
            self.forged_items.append(item)
            return item
        return None

    def reforge(self, item_id):
        # bug6: 无批量
        pass

    def get_forger(self, item_id):
        # bug7: 不记录锻造者
        return "unknown"
