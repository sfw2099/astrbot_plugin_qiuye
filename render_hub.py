# -*- coding: utf-8 -*-
"""秋烨统一渲染：成就图（按插件分组）/ 道具图 / 诗句列表 / 诗句报表。"""

import os

from PIL import Image, ImageDraw, ImageFont

try:
    from .hub import plugin_display
except ImportError:
    from hub import plugin_display

_FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "HarmonyOS_Sans_SC.ttf")
_font_cache = {}


def _get_font(size):
    key = int(size)
    if key not in _font_cache:
        try:
            _font_cache[key] = ImageFont.truetype(_FONT_PATH, key)
        except Exception:
            _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]


# ================= 成就图 =================

def render_achievements(uname, achs, registry, output_path):
    """渲染全插件成就汇总图。

    achs: {ach_id: {"unlocked", "time", "progress", "plugin"}}
    registry: {"achievements": {plugin: {ach_id: {"name","desc"}}}, ...}
    """
    # ach_id -> (name, desc, plugin)
    info_map = {}
    for plugin, bucket in registry.get("achievements", {}).items():
        for ach_id, info in bucket.items():
            info_map[ach_id] = (info.get("name", ach_id), info.get("desc", ""), plugin)

    unlocked, progress_items = {}, {}
    for ach_id, v in achs.items():
        name, desc, plugin = info_map.get(ach_id, (ach_id, "", v.get("plugin", "")))
        plugin = v.get("plugin") or plugin or "其他"
        if v.get("unlocked"):
            unlocked.setdefault(plugin, []).append((ach_id, name, desc, v))
        elif v.get("progress"):
            progress_items.setdefault(plugin, []).append((ach_id, name, desc, v))

    groups = []
    all_plugins = list(unlocked.keys()) + [p for p in progress_items if p not in unlocked]
    for plugin in all_plugins:
        rows = [(True, r) for r in unlocked.get(plugin, [])] + [(False, r) for r in progress_items.get(plugin, [])]
        if rows:
            groups.append((plugin, rows))

    pad = 30
    title_h = 70
    row_h = 40
    head_h = 34
    item_font = _get_font(19)
    title_font = _get_font(26)
    small_font = _get_font(14)
    head_font = _get_font(17)

    total_unlocked = sum(1 for _, rows in groups for ok, _ in rows if ok)
    total_known = max(len(registry.get("achievements", {})) and sum(len(b) for b in registry.get("achievements", {}).values()) or 0, total_unlocked)
    rows_total = sum(len(rows) + 1 for _, rows in groups)
    img_w = 720
    img_h = pad + title_h + rows_total * (row_h + 6) + pad

    img = Image.new("RGB", (img_w, img_h), (250, 250, 252))
    draw = ImageDraw.Draw(img)
    draw.text((img_w // 2, 20), f"[成就] {uname}（{total_unlocked}/{total_known}）", fill=(40, 40, 40), font=title_font, anchor="mt")

    y = pad + title_h
    if not groups:
        draw.text((img_w // 2, y), "（暂无成就，快去玩游戏吧！）", fill=(120, 120, 125), font=item_font, anchor="mm")
        y += row_h + 6
    for plugin, rows in groups:
        draw.text((pad + 14, y + head_h // 2), f"── {plugin_display(plugin)} ──", fill=(90, 130, 200), font=head_font, anchor="lm")
        y += head_h + 4
        for ok, (ach_id, name, desc, v) in rows:
            if ok:
                draw.rounded_rectangle([pad, y, img_w - pad, y + row_h], radius=8, fill=(255, 255, 255),
                                       outline=(200, 200, 205), width=1)
                label = f"[已解锁] {name}"
                fill = (40, 40, 40)
            else:
                draw.rounded_rectangle([pad, y, img_w - pad, y + row_h], radius=8, fill=(248, 248, 250),
                                       outline=(220, 220, 225), width=1)
                label = f"[进行中] {name}"
                fill = (120, 120, 125)
                desc = f"进度：{v.get('progress', 0)}"
            draw.text((pad + 14, y + row_h // 2), label, fill=fill, font=item_font, anchor="lm")
            draw.text((img_w - pad - 14, y + row_h // 2), desc, fill=(150, 150, 155), font=small_font, anchor="rm")
            y += row_h + 6

    img.save(output_path, "PNG")
    return output_path


# ================= 道具图 =================

def render_items(uname, items, registry, output_path):
    """渲染全插件道具汇总图。items: {item_name: count}。"""
    info_map = {}
    for plugin, bucket in registry.get("items", {}).items():
        for item, info in bucket.items():
            info_map[item] = (info.get("desc", ""), plugin)

    groups = {}
    for item, cnt in items.items():
        if not cnt or int(cnt) <= 0:
            continue
        desc, plugin = info_map.get(item, ("", "其他"))
        groups.setdefault(plugin or "其他", []).append((item, int(cnt), desc))

    pad = 30
    title_h = 70
    row_h = 52
    head_h = 34
    title_font = _get_font(26)
    name_font = _get_font(21)
    desc_font = _get_font(15)
    head_font = _get_font(17)

    rows_total = sum(len(v) + 1 for v in groups.values())
    img_w = 760
    img_h = pad + title_h + rows_total * (row_h + 6) + pad

    img = Image.new("RGB", (img_w, img_h), (250, 250, 252))
    draw = ImageDraw.Draw(img)
    draw.text((img_w // 2, 20), f"{uname} 的道具", fill=(40, 40, 40), font=title_font, anchor="mt")

    y = pad + title_h
    if not groups:
        draw.text((img_w // 2, y + 20), "（还没有道具。游戏结算可获得道具，/抽道具 也可抽取）",
                  fill=(120, 120, 125), font=name_font, anchor="mm")
    for plugin in groups:
        draw.text((pad + 14, y + head_h // 2), f"── {plugin_display(plugin)} ──", fill=(90, 130, 200), font=head_font, anchor="lm")
        y += head_h + 4
        for item, cnt, desc in groups[plugin]:
            draw.rounded_rectangle([pad, y, img_w - pad, y + row_h], radius=8, fill=(255, 255, 255),
                                   outline=(200, 200, 205), width=1)
            draw.text((pad + 16, y + row_h // 2), f"{item} x{cnt}", fill=(50, 120, 190), font=name_font, anchor="lm")
            draw.text((pad + 200, y + row_h // 2), desc, fill=(110, 110, 110), font=desc_font, anchor="lm")
            y += row_h + 6

    img.save(output_path, "PNG")
    return output_path


# ================= 诗句列表 =================

def render_verse_list(uname, verses, output_path):
    """渲染玩家积累诗句列表图。verses: {单句: {"first","count"}}。"""
    pad = 30
    title_h = 70
    row_h = 34
    item_font = _get_font(20)
    title_font = _get_font(26)
    col_gap = 18
    per_row = 5

    sorted_items = sorted(verses.items(), key=lambda kv: kv[1].get("first", 0))
    items = [v for v, _ in sorted_items]
    total = len(items)
    rows = (total + per_row - 1) // per_row if total else 1

    cell_w = 150
    img_w = pad * 2 + per_row * cell_w + (per_row - 1) * col_gap
    img_h = pad + title_h + rows * (row_h + 4) + pad

    img = Image.new("RGB", (img_w, img_h), (250, 250, 252))
    draw = ImageDraw.Draw(img)
    draw.text((img_w // 2, 20), f"📚 {uname} 的诗词积累（{total} 句）", fill=(40, 40, 40), font=title_font, anchor="mt")

    y = pad + title_h
    for idx, v in enumerate(items):
        col = idx % per_row
        row = idx // per_row
        x = pad + col * (cell_w + col_gap)
        cy = y + row * (row_h + 4)
        draw.rounded_rectangle([x, cy, x + cell_w, cy + row_h], radius=6, fill=(255, 255, 255),
                               outline=(200, 200, 205), width=1)
        draw.text((x + cell_w // 2, cy + row_h // 2), v, fill=(50, 50, 50), font=item_font, anchor="mm")

    img.save(output_path, "PNG")
    return output_path


# ================= 诗句报表 =================

def render_poetry_report(report, output_path):
    """渲染个人诗句积累分析报表长图（数据由诗词底座收集）。"""
    W = 900
    PAD = 28
    H1 = 70
    H2 = 90
    RH = 40
    SEC = 50
    tfont = _get_font(30)
    sfont = _get_font(24)
    afont = _get_font(20)
    nfont = _get_font(17)

    def sec_title(d, y, text):
        d.text((PAD, y), text, fill=(40, 40, 40), font=sfont)
        return y + 34

    nv = min(8, len(report.get('top_verses', [])))
    na = min(8, len(report.get('top_authors', [])))
    dyn = report.get('dynasties', [])
    wl = report.get('word_len', [])
    tc = report.get('top_chars', [])[:10]
    H = (PAD + H1 + H2 + SEC
         + (34 + nv * RH if nv else 0)
         + SEC + (34 + na * RH if na else 0)
         + SEC + (34 + len(dyn) * RH if dyn else 0)
         + SEC + (34 + (len(wl) or 1) * RH)
         + SEC + (34 + ((len(tc) + 4) // 5) * RH)
         + PAD)
    img = Image.new('RGB', (W, H), (250, 250, 252))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, H], fill=(250, 250, 252))

    import time as _t
    now = _t.strftime('%Y-%m-%d %H:%M')
    d.text((W // 2, 16), "诗句积累分析报表", fill=(30, 30, 30), font=_get_font(34), anchor='mt')
    d.text((W // 2, 62), f"{report.get('uname','')} · {now}", fill=(120, 120, 120), font=nfont, anchor='mt')

    y = PAD + H1
    metrics = [
        ('总单句', report.get('total', 0)),
        ('总使用', report.get('uses', 0)),
        ('重复句', report.get('dup', 0)),
        ('未能识别', report.get('unknown', 0)),
    ]
    cw = (W - PAD * 2) // len(metrics)
    for i, (lab, val) in enumerate(metrics):
        x = PAD + i * cw
        d.rounded_rectangle([x + 8, y + 10, x + cw - 8, y + H2 - 10], radius=10, fill=(255, 255, 255), outline=(210, 210, 215))
        d.text((x + cw // 2, y + 24), str(val), fill=(60, 120, 200), font=_get_font(30), anchor='mt')
        d.text((x + cw // 2, y + 60), lab, fill=(120, 120, 120), font=nfont, anchor='mt')
    y += H2 + SEC

    if nv:
        y = sec_title(d, y, '常用诗句 TOP')
        maxv = max((v.get('count', 0) for v in report['top_verses']), default=1)
        for i, v in enumerate(report['top_verses'][:nv]):
            d.text((PAD, y + RH // 2), f'{i+1}. {v.get("text","")}', fill=(30, 30, 30), font=afont, anchor='lm')
            bw = int((W - PAD * 2 - 190) * (v.get('count', 0) / maxv))
            bx = PAD + 185
            d.rounded_rectangle([bx, y + 8, bx + max(3, bw), y + RH - 8], radius=6, fill=(70, 130, 220))
            d.text((PAD + 190, y + RH // 2), str(v.get('count', 0)), fill=(90, 90, 90), font=nfont, anchor='lm')
            d.text((W - PAD, y + RH // 2), str(v.get('author', '') or '未知'), fill=(150, 150, 150), font=nfont, anchor='rm')
            y += RH
        y += SEC

    if na:
        y = sec_title(d, y, '常用诗人 TOP')
        maxv = max((a.get('count', 0) for a in report['top_authors']), default=1)
        for i, a in enumerate(report['top_authors'][:na]):
            d.text((PAD, y + RH // 2), f'{i+1}. {a.get("name","")}', fill=(30, 30, 30), font=afont, anchor='lm')
            bw = int((W - PAD * 2 - 150) * (a.get('count', 0) / maxv))
            bx = PAD + 145
            d.rounded_rectangle([bx, y + 8, bx + max(3, bw), y + RH - 8], radius=6, fill=(90, 160, 120))
            d.text((PAD + 150, y + RH // 2), str(a.get('count', 0)), fill=(90, 90, 90), font=nfont, anchor='lm')
            y += RH
        y += SEC

    if dyn:
        y = sec_title(d, y, '朝代占比')
        for name, cnt, pct in dyn:
            d.text((PAD, y + RH // 2), name, fill=(40, 40, 40), font=afont, anchor='lm')
            bw = int((W - PAD * 2 - 150) * (pct / 100))
            bx = PAD + 145
            d.rounded_rectangle([bx, y + 8, bx + max(3, bw), y + RH - 8], radius=6, fill=(170, 120, 200))
            d.text((PAD + 150, y + RH // 2), f'{cnt}', fill=(90, 90, 90), font=nfont, anchor='lm')
            d.text((W - PAD, y + RH // 2), f'{pct}%', fill=(150, 150, 150), font=nfont, anchor='rm')
            y += RH
        y += SEC

    y = sec_title(d, y, '字数分布')
    if wl:
        maxv = max((c for _, c in wl), default=1)
        for label, cnt in wl:
            d.text((PAD, y + RH // 2), label, fill=(40, 40, 40), font=afont, anchor='lm')
            bw = int((W - PAD * 2 - 150) * (cnt / maxv))
            bx = PAD + 145
            d.rounded_rectangle([bx, y + 8, bx + max(3, bw), y + RH - 8], radius=6, fill=(220, 150, 90))
            d.text((PAD + 150, y + RH // 2), str(cnt), fill=(90, 90, 90), font=nfont, anchor='lm')
            y += RH
    else:
        d.text((PAD, y + RH // 2), '暂无数据', fill=(150, 150, 150), font=nfont, anchor='lm')
        y += RH
    y += SEC

    y = sec_title(d, y, '常用字 TOP')
    if tc:
        cell_w = (W - PAD * 2) // 5
        for idx, (ch, cnt) in enumerate(tc):
            col = idx % 5
            row = idx // 5
            x = PAD + col * cell_w
            cy = y + row * RH
            d.rounded_rectangle([x + 6, cy + 4, x + cell_w - 6, cy + RH - 4], radius=6, fill=(255, 255, 255), outline=(210, 210, 215))
            d.text((x + 18, cy + RH // 2), ch, fill=(40, 40, 40), font=afont, anchor='lm')
            d.text((x + cell_w - 12, cy + RH // 2), str(cnt), fill=(120, 120, 120), font=nfont, anchor='rm')
        y += (((len(tc) + 4) // 5) + 1) * RH
    else:
        d.text((PAD, y + RH // 2), '暂无数据', fill=(150, 150, 150), font=nfont, anchor='lm')
        y += RH

    img.save(output_path, 'PNG')
    return output_path
