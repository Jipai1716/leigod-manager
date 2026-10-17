#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""青龙定时任务：雷神定时暂停。

行为：
  1. 读青龙环境变量里的 Token
  2. 查询是否已暂停；已暂停则不重复调用暂停接口
  3. 未暂停则调用 /api/user/pause，并复查 pause_status_id 后再判定结果
  4. 记录事件 + 暂停状态，可选推送 QQ

退出码：0 = 成功（含“本来就已暂停”），1 = 失败，2 = 未配置 Token
"""

from __future__ import annotations

import sys

from leigod_common import Config, QinglongClient, Store, do_pause, now, qq_send


def main() -> int:
    cfg = Config()
    ql = QinglongClient(cfg.ql_base, cfg.ql_client_id, cfg.ql_client_secret, cfg.http_timeout)
    store = Store(cfg, ql)

    header = f"[{now(cfg).strftime('%Y-%m-%d %H:%M:%S')}] 雷神定时暂停"
    ok, reply = do_pause(cfg, ql, store, trigger="cron")

    print(header)
    print(reply)

    if "--no-push" not in sys.argv:
        try:
            qq_send(cfg, f"【雷神定时暂停】\n{reply}", markdown=False)
        except Exception as exc:  # noqa: BLE001 - 推送失败不影响任务结论
            print(f"QQ 推送失败: {exc}")

    if "未配置雷神 Token" in reply:
        return 2
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
