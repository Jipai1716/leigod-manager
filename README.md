# 雷神加速器 Token 管理与定时暂停系统

在现有 NAS（青龙面板 + AstrBot/QQ 机器人）上实现，**全程固定指令、不经过大模型**。

```
Via 浏览器（提取 Token）
        │  /l u <Token>
        ▼
AstrBot 插件（固定指令入口，不调用 LLM）
        │
        ├── 读写青龙环境变量 ──> 青龙面板
        │                          ├── 雷神定时暂停（每 6 小时）
        │                          └── 雷神每日日报（23:59）
        └── 调用雷神官网接口 ──> webapi.leigod.com
```

## 快速开始

1. **手机装 Via 用户脚本**：把 `via/leigod-token.user.js` 导入 Via 的用户脚本管理，登录雷神官网后页面右下角出现「提取 Token」。
2. **发指令**：QQ 私聊机器人 `/l u <粘贴的 Token>`。
3. 完事。之后每 6 小时自动暂停，23:59 推日报。

## 指令

| 功能 | 完整 | 简写 |
|---|---|---|
| 帮助 | `/leigod help` | `/l h` |
| 更新 Token | `/leigod update <Token>` | `/l u <Token>` |
| 查询状态 | `/leigod status` | `/l s` |
| 手动暂停 | `/leigod pause` | `/l p` |
| 官网最近 3 条时长日志 | `/leigod logs` | `/l logs` |
| 本地执行记录 | `/leigod history` | `/l hist` |

- 仅**私聊** + **白名单**（`LEIGOD_ALLOWED_IDS`）可用。
- 未知指令、缺参数、多参数一律只回用法，不执行任何脚本。
- Token 原样写入，不转小写、不改字符。

## 关键设计

| 点 | 做法 |
|---|---|
| 不验证 Token 有效性 | 只确认「写入青龙成功」，回复里明确写「有效性验证：未执行」 |
| 不复制暂停逻辑 | `leigod_common.do_pause()` 一份实现，cron 与手动触发都调它 |
| 区分「已触发」与「暂停成功」 | 调用后复查 `pause_status_id`，查不到才算未知 |
| 不动现有任务 | 新建 id 14 / 15 两个任务；原有 5 个任务的脚本、cron、变量零改动 |
| 跨容器状态 | 两容器无共享挂载，事件日志存青龙环境变量 `LEIGOD_CMDLOG`（上限 100 条） |
| 不新增常驻服务 | 复用已运行的 AstrBot 与青龙，无新容器 |

## 目录

```
scripts/                         青龙侧（部署到 /ql/data/scripts/leigod）
  leigod_common.py               公共库：雷神客户端 / 青龙客户端 / QQ 推送 / 事件存储
  leigod_cmd.py                  固定指令解析与分发（插件与命令行共用）
  leigod_pause.py                定时暂停（青龙任务 14）
  leigod_daily_report.py         每日日报（青龙任务 15）
  leigod_update_token.py         手工更新 Token
  leigod_logs.py                 查官网日志
  leigod_status.py               查状态
  leigod_history.py              查本地记录
astrbot_plugin_leigod_manager/   AstrBot 插件（入站指令）
via/leigod-token.user.js         Via 用户脚本
docs/env-survey.md               环境与接口调查记录（含证据）
docs/development.md              实现细节、部署、回滚、排错
tests/                           离线测试
deploy.sh                        服务器端部署脚本
```

## 配置

见 `config.example`。最少需要：

```text
LEIGOD_QL_BASE_URL       青龙地址（容器内 http://127.0.0.1:5700）
LEIGOD_QL_CLIENT_ID      青龙 API 应用 ID
LEIGOD_QL_CLIENT_SECRET  青龙 API 应用密钥
LEIGOD_ALLOWED_IDS       允许执行指令的 QQ openid，逗号分隔
```

QQ 推送复用已有 `QQ_APP_ID` / `QQ_APP_SECRET` / `QQ_OPENID`。

## 部署

```bash
# 1) 打包上传
tar -czf leigod-deploy.tgz scripts astrbot_plugin_leigod_manager via docs
scp leigod-deploy.tgz nas:/tmp/ && ssh nas 'mkdir -p /tmp/leigod-deploy && tar -xzf /tmp/leigod-deploy.tgz -C /tmp/leigod-deploy'

# 2) 服务器端部署（需要 sudo）
ssh nas 'bash /tmp/leigod-deploy/deploy.sh --restart-astrbot'
```

部署后检查：

```bash
docker exec qinglong sh -c 'cd /ql/data/scripts && task leigod/leigod_status.py'
docker logs --since 10m astrbot | grep leigod    # 应看到「指令入口已就绪」
```

## 已知限制

- 雷神 `account_token` 约 **7 天**过期，过期后需重新提取并 `/l u`。系统不会自动刷新。
- `/api/user/pause/lists` 的响应字段在现有 Token 下尚未实测（解析器已做多结构容错，见 `parse_pause_logs`）。
- 跨容器事件日志用青龙环境变量承载，**不支持并发写**（单人低频使用无影响）。
- 官网改版或接口变动时，日志查询会报错而不会伪造数据。

更多见 `docs/development.md`。
