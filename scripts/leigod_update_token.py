#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""更新青龙里的雷神 Token（不验证有效性）。

用法:
  python3 leigod_update_token.py <Token>
  echo <Token> | python3 leigod_update_token.py -
"""

from __future__ import annotations

import sys

from leigod_common import Config, QinglongClient, Store, update_token


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: leigod_update_token.py <Token>")
        return 64
    raw = sys.argv[1]
    if raw == "-":
        raw = sys.stdin.read().strip()
    cfg = Config()
    ql = QinglongClient(cfg.ql_base, cfg.ql_client_id, cfg.ql_client_secret, cfg.http_timeout)
    store = Store(cfg, ql)
    ok, reply = update_token(cfg, ql, store, raw)
    print(reply)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
