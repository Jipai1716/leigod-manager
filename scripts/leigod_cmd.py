#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""固定指令解析与分发。

规则（与开发文档 §3 一致）：
  - 前缀只接受 /leigod 与 /l，大小写不敏感
  - 命令名大小写不敏感
  - Token 原样保留，不转小写、不去掉特殊字符
  - 除 update 外，命令不允许带多余参数
  - 未知命令、参数缺失、参数过多一律只回用法，不执行任何脚本

用法:
  python3 leigod_cmd.py "/l s" --sender <openid> --private
  python3 leigod_cmd.py --selftest
"""

from __future__ import annotations

import sys

from leigod_common import (
    Config,
    QinglongClient,
    Store,
    build_history,
    build_status,
    do_pause,
    fetch_logs,
    update_token,
)

HELP_TEXT = """雷神管理器指令

/l h        帮助
/l u <Token> 更新雷神 Token（不验证有效性）
/l s        查询状态
/l p        手动暂停一次
/l logs     查询官网最近 3 条时长日志
/l hist     查看本地执行记录

完整写法把 /l 换成 /leigod，例如 /leigod status。
仅限白名单用户在私聊中使用。"""

ALIASES = {
    "help": "help",
    "h": "help",
    "update": "update",
    "u": "update",
    "status": "status",
    "s": "status",
    "pause": "pause",
    "p": "pause",
    "logs": "logs",
    "history": "history",
    "hist": "history",
}

ARG_LIMIT = {"help": 0, "status": 0, "pause": 0, "logs": 0, "history": 0}


def parse(text: str) -> tuple[str | None, str | None, str]:
    """返回 (command, token, error)。

    command 为 None 表示消息不是本系统的指令（交给其他处理器）。
    error 非空表示是指令但格式错误。
    """
    raw = (text or "").strip()
    if not raw.startswith("/"):
        return None, None, ""

    body = raw[1:]
    # 前缀
    lowered = body.lower()
    if lowered.startswith("leigod"):
        rest = body[len("leigod") :]
    elif lowered.startswith("l"):
        rest = body[1:]
    else:
        return None, None, ""

    # 前缀后面必须是空白或结束，避免 /login 之类误判
    if rest and not rest[0].isspace():
        return None, None, ""
    rest = rest.strip()

    if not rest:
        return "help", None, ""

    parts = rest.split(None, 1)
    name = parts[0].lower()
    tail = parts[1].strip() if len(parts) > 1 else ""

    command = ALIASES.get(name)
    if command is None:
        return "unknown", None, f"未知指令：{parts[0]}"

    if command == "update":
        if not tail:
            return "update", None, "缺少 Token 参数"
        if any(ch.isspace() for ch in tail):
            return "update", None, "参数过多：Token 中不应包含空白"
        return "update", tail, ""

    if tail:
        return command, None, "该指令不接受参数"
    return command, None, ""


def handle(text: str, sender_id: str = "", is_private: bool = True, cfg: Config | None = None) -> str:
    cfg = cfg or Config()
    command, token, error = parse(text)

    if command is None:
        return ""

    if not is_private:
        return "该指令仅在私聊中可用。"

    if cfg.allowed_ids and sender_id not in cfg.allowed_ids:
        return "无权限：你的账号不在允许列表中。"

    if error:
        return f"{error}\n\n{HELP_TEXT}"

    if command == "help":
        return HELP_TEXT
    if command == "unknown":
        return f"{error}\n\n{HELP_TEXT}"

    ql = QinglongClient(cfg.ql_base, cfg.ql_client_id, cfg.ql_client_secret, cfg.http_timeout)
    store = Store(cfg, ql)

    try:
        if command == "update":
            _ok, reply = update_token(cfg, ql, store, token or "")
            return reply
        if command == "status":
            return build_status(cfg, ql, store)
        if command == "pause":
            _ok, reply = do_pause(cfg, ql, store, trigger="manual")
            return reply
        if command == "logs":
            _ok, reply = fetch_logs(cfg, ql, store, limit=3)
            return reply
        if command == "history":
            return build_history(store, limit=10)
    except Exception as exc:  # noqa: BLE001 - 任何意外都要回话，不能静默
        return f"执行失败：{exc}"

    return "未知指令"


def _selftest() -> int:
    cases = [
        ("/l h", "help", ""),
        ("/leigod help", "help", ""),
        ("/L H", "help", ""),
        ("/leigod status", "status", ""),
        ("/l s", "status", ""),
        ("/l p", "pause", ""),
        ("/l logs", "logs", ""),
        ("/l hist", "history", ""),
        ("/l u abc@DEF_123-xy", "update", "abc@DEF_123-xy"),
        ("/leigod update abc@DEF_123-xy", "update", "abc@DEF_123-xy"),
        ("  /l u TOKEN  ", "update", "TOKEN"),
        ("/login", None, ""),
        ("hello", None, ""),
        ("/l u", "update", ""),
        ("/l s extra", "status", ""),
        ("/l nope", "unknown", ""),
    ]
    failed = 0
    for text, want_cmd, want_token in cases:
        cmd, token, err = parse(text)
        ok = cmd == want_cmd and (want_token == "" or token == want_token)
        if want_cmd in ("update",) and want_token == "":
            ok = cmd == "update" and bool(err)
        if want_cmd in ("status",) and text.endswith("extra"):
            ok = cmd == "status" and bool(err)
        if want_cmd is None:
            ok = cmd is None
        status = "OK  " if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"{status} {text!r:38s} -> cmd={cmd!r} token={token!r} err={err!r}")

    # token 必须原样保留（大小写/特殊字符）
    _c, tok, _e = parse("/l u AbC%$@#123")
    same = tok == "AbC%$@#123"
    print(("OK   " if same else "FAIL ") + f"token 原样保留 -> {tok!r}")
    failed += 0 if same else 1
    print(f"\n{'PASS' if failed == 0 else f'{failed} FAILED'}")
    return 0 if failed == 0 else 1


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return _selftest()
    text = argv[0] if argv else ""
    sender = ""
    private = True
    for idx, arg in enumerate(argv):
        if arg == "--sender" and idx + 1 < len(argv):
            sender = argv[idx + 1]
        if arg == "--group":
            private = False
    print(handle(text, sender_id=sender, is_private=private))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
