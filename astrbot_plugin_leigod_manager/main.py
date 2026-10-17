# -*- coding: utf-8 -*-
"""AstrBot 插件：雷神加速器固定指令入口。

设计要点：
  - 只匹配 /leigod 与 /l 开头的消息，不拦截其他聊天
  - 命中后 stop_event()，绝不进入大模型
  - 仅私聊 + 白名单
  - 业务逻辑复用已部署的 leigod_common / leigod_cmd（同一份实现）

配置来源（优先级从高到低）：
  1. 容器环境变量 LEIGOD_*
  2. 插件目录下 config.json
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))

# 允许用 LEIGOD_LIB_PATH 指向青龙脚本目录，默认用插件目录里的副本
_LIB_DIRS = [
    os.environ.get("LEIGOD_LIB_PATH", ""),
    PLUGIN_DIR,
    os.path.join(PLUGIN_DIR, "lib"),
]
for _dir in _LIB_DIRS:
    if _dir and os.path.isdir(_dir) and _dir not in sys.path:
        sys.path.insert(0, _dir)


def _load_config_file():
    """把插件目录的 config.json 读成环境变量，供公共库使用（不覆盖已有 env）。"""
    path = os.path.join(PLUGIN_DIR, "config.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[leigod] 读取 config.json 失败: {exc}")
        return {}
    mapping = {
        "ql_base": "LEIGOD_QL_BASE_URL",
        "ql_client_id": "LEIGOD_QL_CLIENT_ID",
        "ql_client_secret": "LEIGOD_QL_CLIENT_SECRET",
        "token_env": "LEIGOD_TOKEN_ENV",
        "allowed_ids": "LEIGOD_ALLOWED_IDS",
        "tz": "LEIGOD_TZ",
        "qq_target": "LEIGOD_QQ_TARGET",
        "state_dir": "LEIGOD_STATE_DIR",
    }
    for key, env_name in mapping.items():
        value = data.get(key)
        if isinstance(value, list):
            value = ",".join(str(v) for v in value)
        if value and not os.environ.get(env_name):
            os.environ[env_name] = str(value)
    return data


@register(
    "astrbot_plugin_leigod_manager",
    "Jipai",
    "雷神加速器 Token 管理与定时暂停的固定指令入口（不调用大模型）",
    "1.0.0",
)
class LeigodManagerPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        _load_config_file()
        self._ready = False
        self._handle = None
        try:
            from leigod_cmd import handle as leigod_handle  # noqa: WPS433 - 延迟导入

            self._handle = leigod_handle
            self._ready = True
            logger.info("[leigod] 指令入口已就绪（/leigod 或 /l）")
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[leigod] 加载公共库失败: {exc}")

    @filter.regex(r"^\s*/(?:leigod|l)(?:\s|$)")
    async def on_leigod_command(self, event: AstrMessageEvent):
        """固定指令分发：命中即回答，不进入 LLM。"""
        event.stop_event()

        if not self._ready:
            yield event.plain_result("雷神管理器未就绪：公共库加载失败，请检查插件目录与 config.json。")
            return

        if event.get_group_id():
            yield event.plain_result("该指令仅在私聊中可用。")
            return

        text = event.get_message_str() or ""
        sender = event.get_sender_id() or ""
        try:
            reply = await asyncio.to_thread(self._handle, text, sender, True)
        except Exception as exc:  # noqa: BLE001 - 任何异常都要回话
            logger.error(f"[leigod] 指令执行异常: {exc}")
            yield event.plain_result(f"执行失败：{exc}")
            return

        if reply:
            yield event.plain_result(reply)

    async def terminate(self):
        logger.info("[leigod] 插件已卸载")
