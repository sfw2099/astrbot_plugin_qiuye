# -*- coding: utf-8 -*-
"""OneBot 工具：发消息/撤回、@解析、群成员名解析、JSON 读写。"""

import asyncio
import json
import os
import re

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent


def load_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path: str, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"[qiuye] 保存数据失败: {e}")


def extract_target_id_from_message(event: AstrMessageEvent):
    for component in event.message_obj.message:
        if isinstance(component, Comp.At):
            return str(component.qq)
    raw_text = str(getattr(event, "message_str", "") or "")
    cq_at = re.search(r"\[CQ:at,qq=(\d+)\]", raw_text)
    if cq_at:
        return cq_at.group(1)
    plain_at = re.search(r"@(\d{5,12})", raw_text)
    if plain_at:
        return plain_at.group(1)
    return None


def extract_all_at_from_message(event: AstrMessageEvent):
    at_ids = []
    for component in event.message_obj.message:
        if isinstance(component, Comp.At):
            at_ids.append(str(component.qq))
    if at_ids:
        return at_ids
    raw_text = str(getattr(event, "message_str", "") or "")
    cq_ats = re.findall(r"\[CQ:at,qq=(\d+)\]", raw_text)
    if cq_ats:
        return cq_ats
    plain_ats = re.findall(r"@(\d{5,12})", raw_text)
    if plain_ats:
        return plain_ats
    return []


def resolve_member_name(members: list, user_id: str, fallback: str) -> str:
    for m in members or []:
        if str(m.get("user_id")) == str(user_id):
            return m.get("card") or m.get("nickname") or fallback
    return fallback


async def get_group_members(event: AstrMessageEvent):
    """获取群成员列表；失败返回 []。"""
    try:
        if event.get_platform_name() == "aiocqhttp":
            members = await event.bot.api.call_action(
                "get_group_member_list", group_id=int(event.get_group_id())
            )
            if isinstance(members, dict) and "data" in members and isinstance(members["data"], list):
                members = members["data"]
            return members or []
    except Exception as e:
        logger.warning(f"[qiuye] 获取群成员列表失败: {e}")
    return []


def extract_message_id(resp) -> object | None:
    try:
        if isinstance(resp, dict):
            data = resp.get("data", resp)
            if isinstance(data, dict):
                mid = data.get("message_id")
                if mid is not None:
                    return mid
    except Exception:
        pass
    return None


async def send_onebot_message(event: AstrMessageEvent, message: list):
    """通过 OneBot 发送原生消息段列表，返回 message_id（可能为 None）。"""
    group_id = event.get_group_id()
    if group_id:
        resp = await event.bot.api.call_action(
            "send_group_msg", group_id=int(group_id), message=message
        )
    else:
        resp = await event.bot.api.call_action(
            "send_private_msg", user_id=int(event.get_sender_id()), message=message
        )
    return extract_message_id(resp)


def schedule_onebot_delete_msg(tasks: set, client, *, message_id, delay: int = 5):
    async def _runner():
        await asyncio.sleep(delay)
        try:
            await client.api.call_action("delete_msg", message_id=message_id)
        except Exception as e:
            logger.warning(f"[qiuye] 自动撤回失败: {e}")

    task = asyncio.create_task(_runner())
    tasks.add(task)
    task.add_done_callback(tasks.discard)


def is_allowed_group(group_id: str, config) -> bool:
    whitelist = config.get("whitelist_groups", [])
    blacklist = config.get("blacklist_groups", [])
    gid_str = str(group_id)
    if gid_str in {str(g) for g in blacklist}:
        return False
    if whitelist and gid_str not in {str(g) for g in whitelist}:
        return False
    return True
