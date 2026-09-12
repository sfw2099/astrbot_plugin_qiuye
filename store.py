# -*- coding: utf-8 -*-
"""秋烨统一存储。

- users/{uid}.json   统一个人档案（运势域 / bond / 插件使用记录 / 成就 / 道具 / 抽道具保底）
- daily_counters/{date}.json  每日动作计数（赠予运势/夺取运势等每日上限）
- group_fortune.json 本群运势
- active_users.json  活跃群友池（供求婚插件等读取候选池）
"""

import json
import os
import threading
import time
from datetime import datetime, timedelta

BOND_MIN = 0
BOND_MAX = 99

DEFAULT_USER = {
    "name": "",
    "first_seen": 0.0,
    "last_active": 0.0,
    "fortune": {"today": None, "date": "", "modifications_left": 0},
    "bond": 50,
    "plugins_used": {},   # plugin -> {first, last, count}
    "achievements": {},   # ach_id -> {unlocked, time, progress, plugin}
    "inventory": {},      # item -> count
    "draw_bonus": 0,
}


def _today_key():
    return datetime.now().strftime("%Y-%m-%d")


def _fortune_today():
    return datetime.now().strftime("%Y%m%d")


def clamp_bond(v: int) -> int:
    return max(BOND_MIN, min(BOND_MAX, int(v)))


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


class UserStore:
    """统一个人档案 + 群级每日计数 + 群运势 + 活跃池。"""

    def __init__(self, data_dir: str, max_records: int = 500):
        self.data_dir = data_dir
        self.users_dir = os.path.join(data_dir, "users")
        self.counters_dir = os.path.join(data_dir, "daily_counters")
        self.group_fortune_file = os.path.join(data_dir, "group_fortune.json")
        self.active_file = os.path.join(data_dir, "active_users.json")
        os.makedirs(self.users_dir, exist_ok=True)
        os.makedirs(self.counters_dir, exist_ok=True)
        self._lock = threading.RLock()
        self._max_records = max_records
        self._group_fortune = _load_json(self.group_fortune_file, {})
        self._active = _load_json(self.active_file, {})

    # ================= 用户档案 =================

    def _user_path(self, uid: str) -> str:
        return os.path.join(self.users_dir, f"{uid}.json")

    def get_user(self, uid: str, name: str = "") -> dict:
        with self._lock:
            path = self._user_path(str(uid))
            u = _load_json(path, None)
            if u is None or not isinstance(u, dict):
                now = time.time()
                u = dict(DEFAULT_USER)
                u["uid"] = str(uid)
                u["first_seen"] = now
                u["last_active"] = now
                u["name"] = name or f"用户{uid}"
                _save_json(path, u)
            else:
                changed = False
                for k, v in DEFAULT_USER.items():
                    if k not in u:
                        u[k] = json.loads(json.dumps(v))
                        changed = True
                if name and u.get("name") != name:
                    u["name"] = name
                    changed = True
                u["bond"] = clamp_bond(u.get("bond", 50))
                if changed:
                    _save_json(path, u)
            return u

    def save_user(self, uid: str, user: dict):
        with self._lock:
            user["uid"] = str(uid)
            user["bond"] = clamp_bond(user.get("bond", 50))
            _save_json(self._user_path(str(uid)), user)

    def touch(self, uid: str, name: str = ""):
        with self._lock:
            u = self.get_user(uid, name)
            u["last_active"] = time.time()
            if name:
                u["name"] = name
            self.save_user(uid, u)

    # ---------- 运势域 ----------

    def ensure_fortune_reset(self, uid: str, name: str = "") -> dict:
        with self._lock:
            u = self.get_user(uid, name)
            today = _fortune_today()
            if u["fortune"].get("date") != today:
                u["fortune"] = {"today": None, "date": today, "modifications_left": 0}
                self.save_user(uid, u)
            return u

    def get_fortune(self, uid: str, name: str = ""):
        u = self.ensure_fortune_reset(uid, name)
        return u["fortune"].get("today")

    def set_fortune(self, uid: str, fortune: int, modifications: int = 0, name: str = ""):
        with self._lock:
            u = self.ensure_fortune_reset(uid, name)
            u["fortune"]["today"] = int(fortune)
            u["fortune"]["date"] = _fortune_today()
            u["fortune"]["modifications_left"] = int(modifications)
            self.save_user(uid, u)
            return u

    # ---------- 羁绊（供求婚插件等调用） ----------

    def get_bond(self, uid: str, name: str = "") -> int:
        u = self.get_user(uid, name)
        return clamp_bond(u.get("bond", 50))

    def add_bond(self, uid: str, delta: int, name: str = "") -> int:
        with self._lock:
            u = self.get_user(uid, name)
            u["bond"] = clamp_bond(u.get("bond", 50) + int(delta))
            self.save_user(uid, u)
            return u["bond"]

    # ---------- 插件使用记录 ----------

    def record_plugin_use(self, uid: str, plugin: str, name: str = ""):
        with self._lock:
            u = self.get_user(uid, name)
            now = time.time()
            entry = u["plugins_used"].get(plugin)
            if entry is None:
                u["plugins_used"][plugin] = {"first": now, "last": now, "count": 1}
            else:
                entry["last"] = now
                entry["count"] = int(entry.get("count", 0)) + 1
            self.save_user(uid, u)

    # ---------- 成就 ----------

    def unlock_achievement(self, uid: str, ach_id: str, plugin: str = "", name: str = "") -> bool:
        """解锁成就。返回是否为新解锁。"""
        with self._lock:
            u = self.get_user(uid, name)
            cur = u["achievements"].get(ach_id, {})
            if cur.get("unlocked"):
                return False
            u["achievements"][ach_id] = {
                "unlocked": True,
                "time": time.time(),
                "progress": cur.get("progress", 0),
                "plugin": plugin or cur.get("plugin", ""),
            }
            self.save_user(uid, u)
            return True

    def set_achievement_progress(self, uid: str, ach_id: str, progress: int, plugin: str = "", name: str = "") -> bool:
        with self._lock:
            u = self.get_user(uid, name)
            cur = u["achievements"].get(ach_id, {})
            if cur.get("unlocked"):
                return False
            if int(progress) <= int(cur.get("progress", 0)):
                return False
            u["achievements"][ach_id] = {
                "unlocked": False,
                "time": cur.get("time", 0),
                "progress": int(progress),
                "plugin": plugin or cur.get("plugin", ""),
            }
            self.save_user(uid, u)
            return True

    def get_achievements(self, uid: str) -> dict:
        return self.get_user(uid).get("achievements", {})

    # ---------- 道具 ----------

    def add_item(self, uid: str, item: str, n: int = 1, name: str = "") -> int:
        with self._lock:
            u = self.get_user(uid, name)
            inv = u["inventory"]
            inv[item] = int(inv.get(item, 0)) + int(n)
            self.save_user(uid, u)
            return inv[item]

    def consume_item(self, uid: str, item: str, n: int = 1, name: str = "") -> bool:
        with self._lock:
            u = self.get_user(uid, name)
            inv = u["inventory"]
            cur = int(inv.get(item, 0))
            if cur < n:
                return False
            if cur == n:
                inv.pop(item, None)
            else:
                inv[item] = cur - n
            self.save_user(uid, u)
            return True

    def item_count(self, uid: str, item: str, name: str = "") -> int:
        return int(self.get_user(uid, name).get("inventory", {}).get(item, 0))

    def get_items(self, uid: str, name: str = "") -> dict:
        return dict(self.get_user(uid, name).get("inventory", {}))

    # ---------- 抽道具保底 ----------

    def get_draw_bonus(self, uid: str, name: str = "") -> int:
        return int(self.get_user(uid, name).get("draw_bonus", 0))

    def add_draw_bonus(self, uid: str, step: int, name: str = "") -> int:
        with self._lock:
            u = self.get_user(uid, name)
            u["draw_bonus"] = min(int(u.get("draw_bonus", 0)) + int(step), 90)
            self.save_user(uid, u)
            return u["draw_bonus"]

    def reset_draw_bonus(self, uid: str, name: str = ""):
        with self._lock:
            u = self.get_user(uid, name)
            u["draw_bonus"] = 0
            self.save_user(uid, u)

    # ================= 每日动作计数 =================

    def _counter_path(self, date_key: str) -> str:
        return os.path.join(self.counters_dir, f"{date_key}.json")

    def _cleanup_counters(self):
        cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        try:
            for f in os.listdir(self.counters_dir):
                if f.endswith(".json") and f[:-5] < cutoff:
                    os.remove(os.path.join(self.counters_dir, f))
        except Exception:
            pass

    def get_daily_count(self, group_id: str, uid: str, action: str) -> int:
        data = _load_json(self._counter_path(_today_key()), {})
        return int(data.get(str(group_id), {}).get(str(uid), {}).get(action, 0))

    def incr_daily_count(self, group_id: str, uid: str, action: str) -> int:
        with self._lock:
            path = self._counter_path(_today_key())
            data = _load_json(path, {})
            g = data.setdefault(str(group_id), {}).setdefault(str(uid), {})
            g[action] = int(g.get(action, 0)) + 1
            _save_json(path, data)
            self._cleanup_counters()
            return g[action]

    # ================= 群运势 =================

    def ensure_group_fortune(self, group_id: str) -> dict:
        with self._lock:
            today = _today_key()
            gid = str(group_id)
            if gid not in self._group_fortune:
                self._group_fortune[gid] = {"fortune": 60, "date": today, "today_members": []}
                _save_json(self.group_fortune_file, self._group_fortune)
                return self._group_fortune[gid]
            gd = self._group_fortune[gid]
            if gd.get("date") != today:
                gd["fortune"] = 60
                gd["date"] = today
                gd["today_members"] = []
                _save_json(self.group_fortune_file, self._group_fortune)
            return gd

    def save_group_fortune(self):
        with self._lock:
            _save_json(self.group_fortune_file, self._group_fortune)

    # ================= 活跃池 =================

    def record_active(self, group_id: str, uid: str):
        gid, uid = str(group_id), str(uid)
        if not gid or uid in ("0", ""):
            return
        with self._lock:
            self._active.setdefault(gid, {})[uid] = time.time()
            self._save_active()

    def get_active_pool(self, group_id: str) -> dict:
        return dict(self._active.get(str(group_id), {}))

    def remove_active(self, group_id: str, uids):
        with self._lock:
            g = self._active.get(str(group_id))
            if not g:
                return
            changed = False
            for u in uids:
                if u in g:
                    del g[u]
                    changed = True
            if changed:
                self._save_active()

    def cleanup_inactive(self, group_id: str):
        with self._lock:
            g = self._active.get(str(group_id))
            if not g:
                return
            now, limit = time.time(), 30 * 24 * 3600
            new = {uid: ts for uid, ts in g.items() if (now - ts < limit) and uid != "0"}
            if len(new) != len(g):
                self._active[str(group_id)] = new
                self._save_active()

    def _save_active(self):
        # 活跃总量上限：按时间保留最新 max_records 条
        all_actives = []
        for gid, users in self._active.items():
            if isinstance(users, dict):
                for uid, ts in users.items():
                    all_actives.append((gid, uid, ts))
        if len(all_actives) > self._max_records:
            all_actives.sort(key=lambda x: x[2])
            keep = all_actives[-self._max_records:]
            new_data = {}
            for gid, uid, ts in keep:
                new_data.setdefault(gid, {})[uid] = ts
            self._active.clear()
            self._active.update(new_data)
        _save_json(self.active_file, self._active)
