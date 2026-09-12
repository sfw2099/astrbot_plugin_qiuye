# -*- coding: utf-8 -*-
"""秋烨枢纽插件：签到运势(COC) + 用户中心（插件使用记录/成就/道具统一枢纽与渲染）+ 活跃群友池。

其他插件通过 star 注册表取得本插件实例（context.get_registered_star("astrbot_plugin_qiuye").star_cls），
即可调用 hub.py 中的统一 API（解锁成就/增删道具/记录插件使用/读取运势与羁绊/活跃池）。
"""

import asyncio
import os
import random

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

from .hub import HubAPI
from .store import UserStore
from .fortune import generate_fortune, coc_roll, ai_reply
from .keyword_trigger import KeywordRouter, KeywordRoute, MatchMode
from .onebot_utils import (
    extract_target_id_from_message,
    extract_all_at_from_message,
    resolve_member_name,
    get_group_members,
    is_allowed_group,
)
from .render_hub import render_achievements, render_items, render_verse_list, render_poetry_report

# 运势系关键词路由（求婚系关键词归求婚插件）
_FORTUNE_KEYWORD_ROUTES = (
    KeywordRoute(keyword="赠予运势", action="give_fortune"),
    KeywordRoute(keyword="zyys", action="give_fortune"),
    KeywordRoute(keyword="本群运势", action="group_fortune"),
    KeywordRoute(keyword="bqys", action="group_fortune"),
    KeywordRoute(keyword="夺取运势", action="steal_fortune"),
    KeywordRoute(keyword="dqys", action="steal_fortune"),
)


@register("astrbot_plugin_qiuye", "ALin", "秋烨枢纽-签到运势+用户中心(成就/道具统一枢纽)", "1.0.0")
class QiuyePlugin(HubAPI, Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        Star.__init__(self, context)
        self.config = config
        self.plugin_data_dir = StarTools.get_data_dir("astrbot_plugin_qiuye")
        self.plugin_data_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir = str(self.plugin_data_dir)
        self.store = UserStore(self.data_dir, max_records=int(self.config.get("max_records", 500) or 500))
        self._keyword_router = KeywordRouter(routes=_FORTUNE_KEYWORD_ROUTES)
        self._keyword_handlers = {
            "give_fortune": self._cmd_give_fortune,
            "group_fortune": self._cmd_group_fortune,
            "steal_fortune": self._cmd_steal_fortune,
        }
        self._keyword_trigger_block_prefixes = ("/", "!", "！")
        logger.info(f"[qiuye] 秋烨枢纽已加载。数据目录: {self.data_dir}")

    # ================= 跨插件支持 =================

    def _get_poetry_base(self):
        """懒加载诗词底座实例（/我的诗句 /诗句报表 数据源）。"""
        try:
            meta = self.context.get_registered_star("astrbot_plugin_poetry_base")
            inst = getattr(meta, "star_cls", None)
            if inst is not None:
                return inst
        except Exception:
            pass
        return None

    def _get_keyword_trigger_mode(self) -> MatchMode:
        raw = self.config.get("keyword_trigger_mode", "contains")
        try:
            return MatchMode(str(raw))
        except ValueError:
            return MatchMode.CONTAINS

    # ================= 消息监听 =================

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def keyword_trigger(self, event: AstrMessageEvent):
        if not self.config.get("keyword_trigger_enabled", False):
            return
        message_str = event.message_str
        if not message_str:
            return
        if event.is_at_or_wake_command:
            return
        if message_str.startswith(self._keyword_trigger_block_prefixes):
            return
        mode = self._get_keyword_trigger_mode()
        route = self._keyword_router.match_route(message_str, mode=mode)
        if route is None:
            route = self._keyword_router.match_command_route(message_str)
        if route:
            handler = self._keyword_handlers.get(route.action)
            if handler:
                async for result in handler(event):
                    yield result
                event.stop_event()

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def track_active(self, event: AstrMessageEvent):
        gid = event.get_group_id()
        if gid:
            uid = str(event.get_sender_id())
            bot_id = str(event.get_self_id())
            if uid != bot_id and uid != "0" and is_allowed_group(str(gid), self.config):
                self.store.record_active(gid, uid)
                uname = event.get_sender_name()
                if uname:
                    self.store.touch(uid, uname)
        if False:
            yield None  # 保持 async generator 形态

    # ==================== 签到 ====================

    def _checkin_drop_items(self, user_id: str, user_name: str) -> list:
        """签到随机掉落 5 个道具（从全道具注册表随机）。返回 [(道具名, 数量)]。"""
        import random as _r
        reg = self.get_registry()
        all_items = []
        for plugin, bucket in reg.get("items", {}).items():
            for item in bucket.keys():
                all_items.append(item)
        if not all_items:
            return []
        drops = {}
        for _ in range(5):
            it = _r.choice(all_items)
            drops[it] = drops.get(it, 0) + 1
        result = []
        for it, cnt in drops.items():
            self.store.add_item(user_id, it, cnt, user_name)
            result.append((it, cnt))
        return result

    @filter.command("签到", alias={"今日运势", "今日人品", "jrrp"})
    async def checkin(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        user_name = event.get_sender_name() or f"用户{user_id}"
        max_modify = int(self.config.get("max_modify_attempts", 1) or 1)
        u = self.store.ensure_fortune_reset(user_id, user_name)
        existing_fortune = u["fortune"].get("today")
        if existing_fortune is not None:
            yield event.plain_result(f"{user_name}，今日已签到！运势值：{existing_fortune}")
            return
        rp = generate_fortune(self.config.get("weighted_random", True))
        self.store.set_fortune(user_id, rp, modifications=max_modify, name=user_name)

        group_id = str(event.get_group_id())
        if group_id:
            group_fd = self.store.ensure_group_fortune(group_id)
            if user_id not in group_fd["today_members"]:
                bonus = max(1, min(5, rp // 20 + 1))
                group_fd["fortune"] += bonus
                group_fd["today_members"].append(user_id)
                self.store.save_group_fortune()
        # 签到掉落 5 个随机道具
        try:
            drops = self._checkin_drop_items(user_id, user_name)
        except Exception as e:
            logger.error(f"[qiuye] 签到掉落失败: {e}")
            drops = []
        drop_text = ""
        if drops:
            drop_text = "\n🎁 签到掉落：\n" + "\n".join(f"  · 【{it}】x{cnt}" for it, cnt in drops)
        try:
            ai_text = await ai_reply(self.context, user_name, rp, origin=event.unified_msg_origin)
            if ai_text:
                yield event.plain_result(f"✨ {user_name} 签到成功！运势值：{rp}\n{ai_text}{drop_text}")
                return
        except Exception as e:
            logger.error(f"[qiuye] AI 调用异常: {e}")
        yield event.plain_result(f"✨ {user_name} 签到成功！运势值：{rp}{drop_text}")

    # ==================== 修改运势 (COC 骰子系统) ====================

    @filter.command("修改运势")
    async def modify_fortune(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        user_name = event.get_sender_name() or f"用户{user_id}"
        u = self.store.ensure_fortune_reset(user_id, user_name)
        current_rp = u["fortune"].get("today")
        if current_rp is None:
            yield event.plain_result("请先进行签到")
            return
        remaining = int(u["fortune"].get("modifications_left", 0))
        if remaining <= 0:
            yield event.plain_result(f"{user_name}，今日的修改运势次数已用完！运势值：{current_rp}")
            return

        # COC 判定：技能值 = (100 - 当前运势) + 本群运势 / 2
        group_fd = self.store.ensure_group_fortune(str(event.get_group_id()))
        skill = (100 - current_rp) + group_fd["fortune"] // 2
        result = coc_roll(skill)
        roll, label = result["roll"], result["label"]

        # 先扣减今日修改次数（与原版行为一致：失败也消耗次数）
        u["fortune"]["modifications_left"] = remaining - 1
        self.store.save_user(user_id, u)
        dice_text = f"D100={roll}/{skill} {label}"

        if result["level"] == 0:  # 大成功
            new_rp = max(current_rp + 1, random.randint(95, 99))
            self.store.set_fortune(user_id, new_rp, modifications=remaining - 1, name=user_name)
            try:
                ai_text = await ai_reply(self.context, user_name, new_rp, scene="修改运势", origin=event.unified_msg_origin)
                if ai_text:
                    yield event.plain_result(f"🎲 大成功！{dice_text}\n运势值：{current_rp} → {new_rp}\n{ai_text}")
                    return
            except Exception as e:
                logger.error(f"[qiuye] AI 调用异常: {e}")
            yield event.plain_result(f"🎲 大成功！{dice_text}\n运势值：{current_rp} → {new_rp}")
        elif result["level"] == 5:  # 大失败
            floor = max(1, current_rp - 50)
            new_rp = random.randint(1, max(current_rp, floor))
            self.store.set_fortune(user_id, new_rp, modifications=remaining - 1, name=user_name)
            yield event.plain_result(f"💀 大失败！{dice_text}\n运势值：{current_rp} → {new_rp}")
        elif result["level"] == 1:  # 极难成功
            bonus = random.randint(15, 30)
            new_rp = min(99, current_rp + bonus)
            self.store.set_fortune(user_id, new_rp, modifications=remaining - 1, name=user_name)
            yield event.plain_result(f"✨ 极难成功！{dice_text}\n运势值：{current_rp} → {new_rp} (+{bonus})")
        elif result["level"] == 2:  # 困难成功
            bonus = random.randint(8, 15)
            new_rp = min(99, current_rp + bonus)
            self.store.set_fortune(user_id, new_rp, modifications=remaining - 1, name=user_name)
            yield event.plain_result(f"🌟 困难成功！{dice_text}\n运势值：{current_rp} → {new_rp} (+{bonus})")
        elif result["level"] == 3:  # 常规成功
            bonus = random.randint(1, 8)
            new_rp = min(99, current_rp + bonus)
            self.store.set_fortune(user_id, new_rp, modifications=remaining - 1, name=user_name)
            yield event.plain_result(f"🌸 常规成功！{dice_text}\n运势值：{current_rp} → {new_rp} (+{bonus})")
        else:  # 失败
            yield event.plain_result(f"没能改变命运。{dice_text}")

    # ==================== 赠予运势 ====================

    @filter.command("赠予运势", alias={"zyys"})
    async def give_fortune(self, event: AstrMessageEvent):
        try:
            async for result in self._cmd_give_fortune(event):
                yield result
        except Exception as e:
            logger.error(f"[qiuye] 赠予运势异常: {e}", exc_info=True)
            yield event.plain_result(f"赠予运势出错了：{e}")

    async def _cmd_give_fortune(self, event: AstrMessageEvent):
        if event.is_private_chat():
            yield event.plain_result("此功能仅在群聊中可用哦~")
            return
        user_id = str(event.get_sender_id())
        user_name = event.get_sender_name() or f"用户{user_id}"
        group_id = str(event.get_group_id())
        if not is_allowed_group(group_id, self.config):
            yield event.plain_result("此功能在当前群聊不可用。")
            return

        target_id = extract_target_id_from_message(event)
        cq_at = extract_all_at_from_message(event)

        if not target_id or target_id == user_id:
            # 赠予群体
            if len(cq_at) > 1:
                yield event.plain_result("一次只能赠予一位群友哦~")
                return
            my_fortune = self.store.get_fortune(user_id, user_name)
            if my_fortune is None:
                yield event.plain_result("你今天还没有签到获取运势，无法赠予。")
                return
            if my_fortune < 5:
                yield event.plain_result("你的运势值过低（<5），无法赠予群体。")
                return
            if self.store.get_daily_count(group_id, user_id, "give_fortune") >= 1:
                yield event.plain_result("你今天已经赠予过运势了，每日只能赠予一次哦~")
                return

            new_fortune = max(1, my_fortune - 5)
            u = self.store.get_user(user_id, user_name)
            self.store.set_fortune(user_id, new_fortune, modifications=u["fortune"].get("modifications_left", 0), name=user_name)

            group_fd = self.store.ensure_group_fortune(group_id)
            group_fd["fortune"] += 1
            self.store.save_group_fortune()
            self.store.incr_daily_count(group_id, user_id, "give_fortune")

            yield event.plain_result(
                f"🎁 {user_name} 将运势赠予了群体！\n"
                f"个人运势：{my_fortune} → {new_fortune}（-5）\n"
                f"本群运势 +1，当前：{group_fd['fortune']}"
            )
            return

        # 赠予个人
        if len(cq_at) > 1:
            yield event.plain_result("一次只能赠予一位群友哦~")
            return

        my_fortune = self.store.get_fortune(user_id, user_name)
        target_fortune = self.store.get_fortune(target_id)

        if my_fortune is None:
            yield event.plain_result("你今天还没有签到获取运势，无法赠予。")
            return
        if target_fortune is None:
            yield event.plain_result("对方今天还没有签到获取运势，无法赠予。")
            return
        if my_fortune <= target_fortune:
            yield event.plain_result(f"你的运势（{my_fortune}）不大于对方的运势（{target_fortune}），无法赠予。")
            return
        if self.store.get_daily_count(group_id, user_id, "give_fortune") >= 1:
            yield event.plain_result("你今天已经赠予过运势了，每日只能赠予一次哦~")
            return

        avg = (my_fortune + target_fortune) // 2
        my_u = self.store.get_user(user_id, user_name)
        tg_u = self.store.get_user(target_id)
        self.store.set_fortune(user_id, avg, modifications=my_u["fortune"].get("modifications_left", 0), name=user_name)
        self.store.set_fortune(target_id, avg, modifications=tg_u["fortune"].get("modifications_left", 0))
        self.store.add_bond(user_id, 5, user_name)
        self.store.add_bond(target_id, 5)
        self.store.incr_daily_count(group_id, user_id, "give_fortune")

        target_name = f"用户({target_id})"
        members = await get_group_members(event)
        if members:
            user_name = resolve_member_name(members, user_id=user_id, fallback=user_name)
            target_name = resolve_member_name(members, user_id=target_id, fallback=target_name)

        yield event.plain_result(
            f"🎁 {user_name} 赠予了 {target_name} 运势！\n"
            f"双方运势已平均为：{avg}\n"
            f"双方羁绊值 +5"
        )

    # ==================== 本群运势 ====================

    @filter.command("本群运势", alias={"bqys"})
    async def group_fortune_cmd(self, event: AstrMessageEvent):
        try:
            async for result in self._cmd_group_fortune(event):
                yield result
        except Exception as e:
            logger.error(f"[qiuye] 本群运势异常: {e}", exc_info=True)
            yield event.plain_result(f"本群运势出错了：{e}")

    async def _cmd_group_fortune(self, event: AstrMessageEvent):
        if event.is_private_chat():
            yield event.plain_result("此功能仅在群聊中可用哦~")
            return
        group_id = str(event.get_group_id())
        if not is_allowed_group(group_id, self.config):
            yield event.plain_result("此功能在当前群聊不可用。")
            return
        fd = self.store.ensure_group_fortune(group_id)

        member_map = {}
        for m in await get_group_members(event):
            uid = str(m.get("user_id"))
            member_map[uid] = m.get("card") or m.get("nickname") or f"用户({uid})"

        members = []
        for uid in fd["today_members"]:
            ft = self.store.get_fortune(uid)
            if ft is not None:
                members.append((member_map.get(uid, f"用户({uid})"), ft))
        members.sort(key=lambda x: -x[1])

        lines = [f"📊 本群今日运势：{fd['fortune']}", f"今日签到人数：{len(members)} 人"]
        if members:
            lines.append("")
            for name, ft in members:
                lines.append(f"  {name}：{ft}")
        lines.extend(["", "签到可增加群运势，群运势可提升修改运势成功率"])
        yield event.plain_result("\n".join(lines))

    # ==================== 夺取运势 ====================

    @filter.command("夺取运势", alias={"dqys"})
    async def steal_fortune(self, event: AstrMessageEvent):
        try:
            async for result in self._cmd_steal_fortune(event):
                yield result
        except Exception as e:
            logger.error(f"[qiuye] 夺取运势异常: {e}", exc_info=True)
            yield event.plain_result(f"夺取运势出错了：{e}")

    async def _cmd_steal_fortune(self, event: AstrMessageEvent):
        if event.is_private_chat():
            yield event.plain_result("此功能仅在群聊中可用哦~")
            return
        user_id = str(event.get_sender_id())
        user_name = event.get_sender_name() or f"用户{user_id}"
        group_id = str(event.get_group_id())
        if not is_allowed_group(group_id, self.config):
            yield event.plain_result("此功能在当前群聊不可用。")
            return

        steal_limit = int(self.config.get("steal_limit", 1) or 1)
        if self.store.get_daily_count(group_id, user_id, "steal") >= steal_limit:
            yield event.plain_result(f"今日夺取运势次数已用完 ({self.store.get_daily_count(group_id, user_id, 'steal')}/{steal_limit})。")
            return

        my_fortune = self.store.get_fortune(user_id, user_name)
        if my_fortune is None:
            yield event.plain_result("你今天还没有签到获取运势。")
            return

        target_id = extract_target_id_from_message(event)
        cq_at = extract_all_at_from_message(event)

        if target_id and target_id != user_id:
            if len(cq_at) > 1:
                yield event.plain_result("一次只能夺取一个人的运势哦~")
                return
            # ---- 夺取个人 ----
            target_fortune = self.store.get_fortune(target_id)
            if target_fortune is None:
                yield event.plain_result("对方今天还没有签到获取运势。")
                return

            skill = my_fortune
            roll_result = coc_roll(skill)
            dice_text = f"D100={roll_result['roll']}/{skill} {roll_result['label']}"
            self.store.incr_daily_count(group_id, user_id, "steal")

            if roll_result["level"] == 0:  # 大成功
                take = (target_fortune + 1) // 2
                new_my = min(99, my_fortune + take)
                new_target = max(1, target_fortune - take)
                u = self.store.get_user(user_id, user_name)
                self.store.set_fortune(user_id, new_my, modifications=u["fortune"].get("modifications_left", 0), name=user_name)
                self.store.set_fortune(target_id, new_target)
                self.store.add_bond(user_id, 10, user_name)
                yield event.plain_result(f"🌟 大成功！{dice_text}\n夺取了对方一半运势（+{take}），当前运势：{new_my}\n羁绊 +10")
                return
            elif roll_result["level"] == 5:  # 大失败
                lose = (my_fortune + 1) // 2
                new_my = max(1, my_fortune - lose)
                new_target = min(99, target_fortune + lose)
                u = self.store.get_user(user_id, user_name)
                self.store.set_fortune(user_id, new_my, modifications=u["fortune"].get("modifications_left", 0), name=user_name)
                self.store.set_fortune(target_id, new_target)
                self.store.add_bond(user_id, -5, user_name)
                yield event.plain_result(f"💀 大失败！{dice_text}\n损失了一半运势（-{lose}），当前运势：{new_my}\n羁绊 -5")
                return
            elif roll_result["level"] <= 3:  # 成功
                new_my = min(99, my_fortune + 10)
                new_target = max(1, target_fortune - 10)
                u = self.store.get_user(user_id, user_name)
                self.store.set_fortune(user_id, new_my, modifications=u["fortune"].get("modifications_left", 0), name=user_name)
                self.store.set_fortune(target_id, new_target)
                yield event.plain_result(f"✅ 夺取成功！{dice_text}\n夺取了 10 点运势，当前运势：{new_my}")
                return
            else:  # 失败
                new_my = max(1, my_fortune - 10)
                new_target = min(99, target_fortune + 10)
                u = self.store.get_user(user_id, user_name)
                self.store.set_fortune(user_id, new_my, modifications=u["fortune"].get("modifications_left", 0), name=user_name)
                self.store.set_fortune(target_id, new_target)
                yield event.plain_result(f"❌ 夺取失败！{dice_text}\n反被夺走 10 点运势，当前运势：{new_my}")
                return
        else:
            # ---- 夺取群体 ----
            skill = my_fortune // 2
            roll_result = coc_roll(skill)
            dice_text = f"D100={roll_result['roll']}/{skill} {roll_result['label']}"
            group_fd = self.store.ensure_group_fortune(group_id)
            self.store.incr_daily_count(group_id, user_id, "steal")

            if roll_result["level"] == 0:  # 大成功
                group_fd["fortune"] -= 5
                new_my = min(99, my_fortune + 25)
                u = self.store.get_user(user_id, user_name)
                self.store.set_fortune(user_id, new_my, modifications=u["fortune"].get("modifications_left", 0), name=user_name)
                self.store.add_bond(user_id, 10, user_name)
                self.store.save_group_fortune()
                yield event.plain_result(f"🌟 大成功！{dice_text}\n从群运势夺走 5 点，个人运势 +25，当前运势：{new_my}\n群运势：{group_fd['fortune']}\n羁绊 +10")
                return
            elif roll_result["level"] == 5:  # 大失败
                lose = (my_fortune + 1) // 2
                new_my = max(1, my_fortune - lose)
                group_fd["fortune"] += lose // 5
                u = self.store.get_user(user_id, user_name)
                self.store.set_fortune(user_id, new_my, modifications=u["fortune"].get("modifications_left", 0), name=user_name)
                self.store.add_bond(user_id, -5, user_name)
                self.store.save_group_fortune()
                yield event.plain_result(f"💀 大失败！{dice_text}\n损失了一半运势（-{lose}），当前运势：{new_my}\n群运势 +{lose // 5}，当前：{group_fd['fortune']}\n羁绊 -5")
                return
            elif roll_result["level"] <= 1:  # 极难成功
                group_fd["fortune"] -= 4
                new_my = min(99, my_fortune + 20)
                u = self.store.get_user(user_id, user_name)
                self.store.set_fortune(user_id, new_my, modifications=u["fortune"].get("modifications_left", 0), name=user_name)
                self.store.save_group_fortune()
                yield event.plain_result(f"✨ 极难成功！{dice_text}\n从群运势夺走 4 点，个人运势 +20，当前运势：{new_my}\n群运势：{group_fd['fortune']}")
                return
            elif roll_result["level"] <= 2:  # 困难成功
                group_fd["fortune"] -= 3
                new_my = min(99, my_fortune + 15)
                u = self.store.get_user(user_id, user_name)
                self.store.set_fortune(user_id, new_my, modifications=u["fortune"].get("modifications_left", 0), name=user_name)
                self.store.save_group_fortune()
                yield event.plain_result(f"🌟 困难成功！{dice_text}\n从群运势夺走 3 点，个人运势 +15，当前运势：{new_my}\n群运势：{group_fd['fortune']}")
                return
            elif roll_result["level"] <= 3:  # 常规成功
                group_fd["fortune"] -= 2
                new_my = min(99, my_fortune + 10)
                u = self.store.get_user(user_id, user_name)
                self.store.set_fortune(user_id, new_my, modifications=u["fortune"].get("modifications_left", 0), name=user_name)
                self.store.save_group_fortune()
                yield event.plain_result(f"🌸 常规成功！{dice_text}\n从群运势夺走 2 点，个人运势 +10，当前运势：{new_my}\n群运势：{group_fd['fortune']}")
                return
            else:  # 失败
                yield event.plain_result(f"夺取失败，未造成影响。{dice_text}")
                return

    # ==================== 用户中心（统一渲染） ====================

    @filter.command("我的成就")
    async def my_achievements(self, event: AstrMessageEvent):
        uid = str(event.get_sender_id())
        uname = event.get_sender_name() or f"用户{uid}"
        achs = self.store.get_achievements(uid)
        img_path = os.path.join(self.data_dir, f"my_achievements_{uid}.png")
        render_achievements(uname, achs, self.get_registry(), img_path)
        yield event.image_result(img_path)

    @filter.command("我的道具", alias={"我的背包"})
    async def my_items(self, event: AstrMessageEvent):
        uid = str(event.get_sender_id())
        uname = event.get_sender_name() or f"用户{uid}"
        inv = self.store.get_items(uid, uname)
        img_path = os.path.join(self.data_dir, f"my_items_{uid}.png")
        render_items(uname, inv, self.get_registry(), img_path)
        yield event.image_result(img_path)

    # ==================== 诗句查询（数据来自诗词底座） ====================

    @filter.command("我的诗句")
    async def my_verses(self, event: AstrMessageEvent):
        uid = str(event.get_sender_id())
        uname = event.get_sender_name() or f"用户{uid}"
        base = self._get_poetry_base()
        if base is None:
            yield event.plain_result("诗词底座插件未安装，暂时无法查询诗句积累。")
            return
        verses = base.get_verses(uid)
        if not verses:
            yield event.plain_result(f"{uname} 还没有积累任何诗句，快去参与猜诗句/诗词对垒吧！")
            return
        img_path = os.path.join(self.data_dir, f"my_verses_{uid}.png")
        render_verse_list(uname, verses, img_path)
        yield event.plain_result(f"📚 {uname} 已积累 {len(verses)} 句诗：")
        yield event.image_result(img_path)

    @filter.command("诗句报表")
    async def verse_report(self, event: AstrMessageEvent):
        uid = str(event.get_sender_id())
        uname = event.get_sender_name() or f"用户{uid}"
        base = self._get_poetry_base()
        if base is None:
            yield event.plain_result("诗词底座插件未安装，暂时无法生成诗句报表。")
            return
        report = await asyncio.to_thread(base.build_verse_report, uid, uname)
        if not report:
            yield event.plain_result(f"{uname} 还没有积累任何诗句，快去参与猜诗句/诗词对垒吧！")
            return
        img_path = os.path.join(self.data_dir, f"verse_report_{uid}.png")
        render_poetry_report(report, img_path)
        yield event.image_result(img_path)

    async def terminate(self):
        pass
