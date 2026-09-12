# -*- coding: utf-8 -*-
"""秋烨枢纽 API：子插件通过 AstrBot star 注册表取得秋烨实例后调用本模块方法。

子插件获取枢纽实例的标准写法（子插件内自行实现，因插件目录不在 sys.path）：

    def get_hub(context):
        try:
            meta = context.get_registered_star("astrbot_plugin_qiuye")
            inst = getattr(meta, "star_cls", None)
            if inst is not None and getattr(inst, "hub_ready", False):
                return inst
        except Exception:
            pass
        return None

枢纽实例即 HubAPI（插件类继承 HubAPI），可直接调用下列方法。
"""

import json
import os
import threading
import time

REGISTRY_FILE = "registry.json"

# 插件注册名 -> 展示名（渲染分组用；未列出的用注册名）
PLUGIN_DISPLAY = {
    "astrbot_plugin_qiuye": "秋烨",
    "astrbot_plugin_qiuhun": "求婚",
    "astrbot_plugin_poetry_base": "诗词底座",
    "astrbot_plugin_poetry_guess": "猜诗句",
    "astrbot_plugin_poetry_flower": "飞花令",
    "astrbot_plugin_rollpig_plus": "今日小猪",
}


def plugin_display(name: str) -> str:
    return PLUGIN_DISPLAY.get(name, name)


class HubAPI:
    """成就/道具注册表 + 统一个人数据 API。插件类继承本类。"""

    hub_ready = True

    # ================= 注册表 =================

    def _registry_path(self) -> str:
        return os.path.join(self.data_dir, REGISTRY_FILE)

    def _load_registry(self) -> dict:
        try:
            with open(self._registry_path(), "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"achievements": {}, "items": {}}

    def _save_registry(self, reg: dict):
        os.makedirs(self.data_dir, exist_ok=True)
        tmp = self._registry_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(reg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self._registry_path())

    def register_achievements(self, plugin: str, achs: dict):
        """子插件注册成就清单。achs: {ach_id: (名称, 描述)} 或 {ach_id: {"name","desc"}}。"""
        reg = self._load_registry()
        bucket = reg.setdefault("achievements", {}).setdefault(plugin, {})
        for ach_id, val in achs.items():
            if isinstance(val, (list, tuple)):
                bucket[str(ach_id)] = {"name": str(val[0]), "desc": str(val[1]) if len(val) > 1 else ""}
            else:
                bucket[str(ach_id)] = {"name": str(val.get("name", ach_id)), "desc": str(val.get("desc", ""))}
        self._save_registry(reg)

    def register_items(self, plugin: str, items: dict):
        """子插件注册道具清单。items: {item_name: 描述} 或 {item_name: {"desc"}}。"""
        reg = self._load_registry()
        bucket = reg.setdefault("items", {}).setdefault(plugin, {})
        for item, val in items.items():
            if isinstance(val, (list, tuple)):
                bucket[str(item)] = {"desc": str(val[0]) if val else ""}
            elif isinstance(val, dict):
                bucket[str(item)] = {"desc": str(val.get("desc", ""))}
            else:
                bucket[str(item)] = {"desc": str(val)}
        self._save_registry(reg)

    def get_registry(self) -> dict:
        return self._load_registry()

    def ach_info(self, ach_id: str):
        """返回 (展示名, 描述, plugin)。查不到时回退 (ach_id, '', '')。"""
        reg = self._load_registry()
        for plugin, bucket in reg.get("achievements", {}).items():
            if ach_id in bucket:
                info = bucket[ach_id]
                return info.get("name", ach_id), info.get("desc", ""), plugin
        return ach_id, "", ""

    def item_info(self, item: str):
        reg = self._load_registry()
        for plugin, bucket in reg.get("items", {}).items():
            if item in bucket:
                return bucket[item].get("desc", ""), plugin
        return "", ""

    # ================= 成就 API =================

    def unlock_achievement(self, uid: str, ach_id: str, plugin: str = "", name: str = "") -> bool:
        """解锁成就。返回是否为新解锁（已解锁返回 False）。"""
        return self.store.unlock_achievement(uid, ach_id, plugin=plugin, name=name)

    def set_achievement_progress(self, uid: str, ach_id: str, progress: int, plugin: str = "", name: str = "") -> bool:
        return self.store.set_achievement_progress(uid, ach_id, progress, plugin=plugin, name=name)

    def get_achievements(self, uid: str) -> dict:
        return self.store.get_achievements(uid)

    # ================= 道具 API =================

    def add_item(self, uid: str, item: str, n: int = 1, name: str = "") -> int:
        return self.store.add_item(uid, item, n, name)

    def consume_item(self, uid: str, item: str, n: int = 1, name: str = "") -> bool:
        return self.store.consume_item(uid, item, n, name)

    def item_count(self, uid: str, item: str, name: str = "") -> int:
        return self.store.item_count(uid, item, name)

    def get_items(self, uid: str, name: str = "") -> dict:
        return self.store.get_items(uid, name)

    # ================= 抽道具保底 API =================

    def get_draw_bonus(self, uid: str, name: str = "") -> int:
        return self.store.get_draw_bonus(uid, name)

    def add_draw_bonus(self, uid: str, step: int, name: str = "") -> int:
        return self.store.add_draw_bonus(uid, step, name)

    def reset_draw_bonus(self, uid: str, name: str = ""):
        self.store.reset_draw_bonus(uid, name)

    # ================= 个人数据 API =================

    def record_plugin_use(self, uid: str, plugin: str, name: str = ""):
        """记录「该用户使用过某插件」。"""
        self.store.record_plugin_use(uid, plugin, name)

    def get_user(self, uid: str, name: str = "") -> dict:
        return self.store.get_user(uid, name)

    def get_fortune(self, uid: str, name: str = ""):
        return self.store.get_fortune(uid, name)

    def set_fortune(self, uid: str, fortune: int, modifications: int = 0, name: str = ""):
        return self.store.set_fortune(uid, fortune, modifications, name)

    def get_bond(self, uid: str, name: str = "") -> int:
        return self.store.get_bond(uid, name)

    def add_bond(self, uid: str, delta: int, name: str = "") -> int:
        return self.store.add_bond(uid, delta, name)

    def get_active_pool(self, group_id: str) -> dict:
        """活跃群友池 {uid: last_ts}（求婚插件抽老婆候选池用）。"""
        return self.store.get_active_pool(group_id)

    def get_group_fortune(self, group_id: str) -> dict:
        return self.store.ensure_group_fortune(group_id)
