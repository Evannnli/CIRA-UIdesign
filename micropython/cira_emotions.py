# -*- coding: utf-8 -*-
"""
CIRA 情绪-光色定义（9+1 种）
==========================

每个情绪对应一组「光生命体」的主色与形态参数。
face.py / 光生命体渲染器根据这些参数在 360×360 圆屏上绘制。

⚠ 视觉方向（Evan 2026-08-06 定）：
- 主体 = **光生命体**（粒子光团），**不是脸、不是光之种子（具象种子造型）**。
- 配色 = 暖橙 / 软粉 / 紫 / 白，背景黑；**禁高饱和蓝**。
- 本文件只定义「色彩 + 形态参数」。眼睛/眉/嘴(eyes/brows/mouth) 字段为旧脸模型遗留，
  正由光生命体渲染器取代；在新渲染器落地前保留以便旧 face.py 不报错。

颜色用 16-bit RGB565（0xRRGGBB 会被转）。
"""

# 目标调色板（Evan 确认 HEX → RGB565）
C_BG     = 0x0000   # 黑底（突出数字生命）
C_CORE   = 0xFFFF   # 白  #FFFFFF（核心意识 / 平静态主色）
C_WARM   = 0xFC47   # 暖橙 #FF8A3D（活力 / 开心 / 聆听 / 回应）
C_PINK   = 0xFCF6   # 软粉 #FF9EB5（亲密 / 安慰）
C_PURPLE = 0xAC7C   # 紫  #A98CE0（思考 / 想象）

EMOTIONS = {
    "happy":    {"eyes": "open",  "mouth": 0.7, "brows": "flat", "tint": C_WARM,   "z": False},
    "excited":  {"eyes": "wide",  "mouth": 0.9, "brows": "up",   "tint": C_WARM,   "z": False},
    "curious":  {"eyes": "open",  "mouth": 0.2, "brows": "up",   "tint": C_WARM,   "z": False},
    "thinking": {"eyes": "half",  "mouth": 0.1, "brows": "flat", "tint": C_PURPLE, "z": False},
    "comfort":  {"eyes": "open",  "mouth": 0.5, "brows": "flat", "tint": C_PINK,   "z": False},
    "worried":  {"eyes": "open",  "mouth": -0.6,"brows": "down", "tint": C_CORE,   "z": False},
    "proud":    {"eyes": "open",  "mouth": 0.8, "brows": "up",   "tint": C_WARM,   "z": False},
    "sleepy":   {"eyes": "half",  "mouth": 0.15,"brows": "none", "tint": C_CORE,   "z": True},
    "neutral":  {"eyes": "open",  "mouth": 0.0, "brows": "flat", "tint": C_CORE,   "z": False},
    "waiting":  {"eyes": "open",  "mouth": 0.0, "brows": "flat", "tint": C_CORE,   "z": False},
}

DEFAULT_EMOTION = "neutral"

# 合法值集合（给 net/main 校验服务端返回用）
VALID = set(EMOTIONS.keys())


def spec(name):
    return EMOTIONS.get(name, EMOTIONS[DEFAULT_EMOTION])
