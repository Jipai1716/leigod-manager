#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打印最近 N 条本地执行记录（默认 10 条）。"""

from __future__ import annotations

import sys

from leigod_common import Config, QinglongClient, Store, build_history


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 10
    cfg = Config()
    ql = QinglongClient(cfg.ql_base, cfg.ql_client_id, cfg.ql_client_secret, cfg.http_timeout)
    store = Store(cfg, ql)
    print(build_history(store, limit=limit))
    return 0


if __name__ == "__main__":
    sys.exit(main())
