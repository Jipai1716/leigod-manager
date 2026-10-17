#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""青龙定时任务：每日运行日志推送。

依赖青龙环境变量里的事件记录（LEIGOD_CMDLOG）。没有记录的项目明确写“无”。
退出码：0 = 推送成功，1 = 推送失败。
"""

from __future__ import annotations

import sys

from leigod_common import Config, QinglongClient, Store, build_daily_report, now, qq_send


def main() -> int:
    cfg = Config()
    ql = QinglongClient(cfg.ql_base, cfg.ql_client_id, cfg.ql_client_secret, cfg.http_timeout)
    store = Store(cfg, ql)

    report = build_daily_report(cfg, store)
    print(report)

    if "--dry-run" in sys.argv:
        return 0

    try:
        channel = qq_send(cfg, report, markdown=False)
        store.add_event("daily_report", "成功", f"channel={channel}")
        print(f"\n已推送（{channel}）")
        return 0
    except Exception as exc:  # noqa: BLE001
        store.add_event("daily_report", "失败", str(exc))
        print(f"\n推送失败: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
