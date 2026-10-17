#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查询雷神官网最近 N 条时长日志（默认 3 条，只读）。

用法:
  python3 leigod_logs.py [N]
"""

from __future__ import annotations

import sys

from leigod_common import Config, QinglongClient, Store, fetch_logs


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 3
    cfg = Config()
    ql = QinglongClient(cfg.ql_base, cfg.ql_client_id, cfg.ql_client_secret, cfg.http_timeout)
    store = Store(cfg, ql)
    ok, reply = fetch_logs(cfg, ql, store, limit=limit)
    print(reply)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
