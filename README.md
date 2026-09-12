# astrbot_plugin_qiuye（秋烨枢纽）

秋烨是本套插件的**中心枢纽**：签到运势（COC 骰子）+ 用户中心（插件使用记录 / 成就 / 道具统一存放与渲染）+ 活跃群友池。

## 指令

| 指令 | 别名 | 说明 |
|---|---|---|
| 签到 | 今日运势 / 今日人品 / jrrp | 每日签到获取运势值（1-99，可加权） |
| 修改运势 | — | COC 骰子判定重投运势（受群运势加成，每日限次） |
| 赠予运势 | zyys | 赠予个人（平均双方运势、羁绊+5）或群体（-5 换群运势+1），每日 1 次 |
| 本群运势 | bqys | 查看本群运势与今日签到名单 |
| 夺取运势 | dqys | 夺取个人/群体运势（COC 判定），每日限次 |
| 我的成就 | — | **全插件成就汇总图**（各子插件成就统一在此渲染） |
| 我的道具 | — | **全插件道具汇总图**（统一背包） |
| 我的诗句 | — | 诗句积累列表（数据来自诗词底座插件） |
| 诗句报表 | — | 诗句积累分析报表（数据来自诗词底座插件） |

## 作为枢纽被其他插件调用

子插件通过 star 注册表获取本插件实例并调用统一 API：

```python
meta = context.get_registered_star("astrbot_plugin_qiuye")
hub = getattr(meta, "star_cls", None)   # 即本插件实例
hub.unlock_achievement(uid, "ach_id", plugin="poetry_guess")
hub.add_item(uid, "火眼金睛", 1)
hub.record_plugin_use(uid, "poetry_guess")
hub.get_fortune(uid) / hub.get_bond(uid) / hub.add_bond(uid, 5)
hub.get_active_pool(group_id)   # 活跃群友池（求婚插件抽老婆候选池）
hub.register_achievements(plugin_name, achs_dict)  # 启动时注册成就清单
hub.register_items(plugin_name, items_dict)
```

## 数据布局

```
data/astrbot_plugin_qiuye/
  users/{uid}.json            # 统一个人档案（运势/羁绊/插件使用/成就/道具/抽道具保底）
  daily_counters/{date}.json  # 每日动作计数（赠予/夺取运势等每日上限）
  group_fortune.json          # 本群运势
  active_users.json           # 活跃群友池
  registry.json               # 各子插件成就/道具注册表
```

## 从旧版 autumn_blaze 迁移（手动）

| 旧 | 新 |
|---|---|
| `autumn_blaze/profiles/{uid}.json` 的 `today_fortune/fortune_date/modifications_left` | `users/{uid}.json` → `fortune` |
| 同文件的 `bond` | `users/{uid}.json` → `bond` |
| `autumn_blaze/group_fortune.json` | 同名直接复制 |
| `autumn_blaze/active_users.json` | 同名直接复制 |
| 其余（records/、forced_marriage.json、profiles 其余字段） | 归求婚插件 astrbot_plugin_qiuhun |
