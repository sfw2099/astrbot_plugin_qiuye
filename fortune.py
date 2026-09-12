# -*- coding: utf-8 -*-
"""运势生成 + COC 骰子 + AI 点评。"""

import random

from astrbot.api import logger


def generate_fortune(is_weighted: bool) -> int:
    if is_weighted:
        weights = [1, 3, 3, 1]
        ranges = [(1, 20), (21, 50), (51, 80), (81, 99)]
        selected_range = random.choices(ranges, weights=weights, k=1)[0]
        return random.randint(selected_range[0], selected_range[1])
    return random.randint(1, 99)


def coc_roll(skill: int) -> dict:
    """投 1d100，返回 {roll, skill, level: 0大成功|1极难|2困难|3常规|4失败|5大失败, label}。"""
    roll = random.randint(1, 100)
    if roll <= 5:
        return {"roll": roll, "skill": skill, "level": 0, "label": "大成功"}
    if roll >= 96:
        return {"roll": roll, "skill": skill, "level": 5, "label": "大失败"}
    if roll <= skill // 5:
        return {"roll": roll, "skill": skill, "level": 1, "label": "极难成功"}
    if roll <= skill // 2:
        return {"roll": roll, "skill": skill, "level": 2, "label": "困难成功"}
    if roll <= skill:
        return {"roll": roll, "skill": skill, "level": 3, "label": "常规成功"}
    return {"roll": roll, "skill": skill, "level": 4, "label": "失败"}


async def ai_reply(context, user_name: str, rp: int, scene: str = "签到", origin: str = ""):
    """生成运势 AI 点评；失败返回 None。"""
    provider = context.get_using_provider()
    if not provider:
        return None
    system_prompt = ""
    try:
        personality = await context.persona_manager.get_default_persona_v3(origin)
        if personality:
            system_prompt = personality["prompt"]
    except Exception as e:
        logger.warning(f"[qiuye] 获取人格失败: {e}")
    if scene == "签到":
        prompt = (
            f"用户 {user_name} 刚刚进行了每日签到，抽到的运势值为 {rp}（满分100）。"
            f"请根据运势值回应：>70 热情夸赞鼓励，<30 温柔安慰鼓励，30~70 平淡带过。"
            f"回复控制在60字以内。"
        )
    else:
        prompt = (
            f"用户 {user_name} 修改了自己的运势值，新的运势值为 {rp}（满分100）。"
            f"请根据运势值回应：>70 热情夸赞鼓励，<30 温柔安慰鼓励，30~70 平淡带过。"
            f"回复控制在60字以内。"
        )
    response = await provider.text_chat(prompt=prompt, system_prompt=system_prompt)
    return response.completion_text or None
