#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打印当前状态（Token 是否已配置、最近一次更新/暂停/日志查询结果）。"""

from __future__ import annotations

import sys

from leigod_common import Config, QinglongClient, Store, build_status


def main() -> int:
    cfg = Config()
    ql = QinglongClient(cfg.ql_base, cfg.ql_client_id, cfg.ql_client_secret, cfg.http_timeout)
    store = Store(cfg, ql)
    print(build_status(cfg, ql, store))
    return 0


if __name__ == "__main__":
    sys.exit(main())
