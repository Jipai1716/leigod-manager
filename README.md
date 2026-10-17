# leigod-manager

雷神加速器（Leigod）Token 管理与定时暂停。用一个自包含的 Docker Web 面板做控制台，
借青龙面板存 Token 并跑定时任务，失败时通过 QQ 机器人报警。

不调用大模型、不自动登录、不刷新 Token、不验证 Token 有效性。

## 功能

- **暂停状态**：实时查询官网 `pause_status_id`，显示「已暂停 / 未暂停 / 未知」，不做本地推断
- **定时暂停**：cron 可在线编辑，内置工作日 / 休息日 / 每 N 小时等预设，保存后回读校验
- **Token 管理**：面板粘贴即可更新，只确认写入成功，明确标注「有效性验证：未执行」
- **时长日志**：读取官网最近 N 条暂停记录（暂停时间 / 恢复时间 / 状态码）
- **失败报警**：定时暂停或手动暂停失败时推送 QQ，成功不打扰
- **浏览器取 Token**：提供 Tampermonkey 与 Via 两份用户脚本

## 工作原理

```
浏览器用户脚本 / 手动粘贴
        │  account_token
        ▼
leigod-manager 面板（Docker，:5788）
        │
        ├── 写环境变量、改 cron  ──► 青龙面板
        │                             ├── 环境变量 LEIGOD_TOKEN（Token 存放处）
        │                             └── 定时任务：按 cron 执行 leigod_pause.py
        │                                          │
        │                                          ▼
        │                                  雷神 webapi.leigod.com
        │                                          │ 仅失败/未知
        │                                          ▼
        └── 读状态与事件记录 ◄──────────────  QQ 机器人报警
```

面板本身**无状态**：Token、事件、暂停结果、定时规则全部通过青龙 OpenAPI 读写，
容器删掉重建不丢数据。

## 环境要求

| 项 | 要求 |
|---|---|
| 主机 | Linux（x86_64 / arm64 均可），已装 Docker |
| 青龙面板 | ≥ 2.16（在 2.21.0-16 上验证）。需要其 OpenAPI 应用具备 `envs`、`crons` 权限 |
| Python | 面板镜像自带 3.11（`python:3.11-slim`），宿主机无需 Python |
| 网络 | 面板容器能访问青龙面板端口与 `webapi.leigod.com` |
| 可选 | QQ 机器人（官方 OpenAPI，用于失败报警） |
| 可选 | Tampermonkey 或 Via 浏览器，用于一键提取 Token |

> 青龙 2.21 的 OpenAPI 前缀是 `/open`（内部重写到 `/api`），鉴权为
> `GET /open/auth/token?client_id=&client_secret=`，注意不是常见的 POST + `{appKey,appSecret}`。

## 部署

### 1. 青龙侧准备

1. 后台「应用设置」新建一个 API 应用，勾选 **环境变量（envs）** 和 **定时任务（crons）**；
   记下 `client_id` 与 `client_secret`。
2. 把本项目 `scripts/` 下的文件放到青龙的脚本目录（容器内 `/ql/data/scripts/leigod/`）。
3. 「定时任务」新建：

   | 名称 | 命令 | 建议 cron |
   |---|---|---|
   | 雷神定时暂停 | `task leigod/leigod_pause.py` | `0 */6 * * *` |

4. 需要 QQ 报警时，配好 `QQ_APP_ID` / `QQ_APP_SECRET` / `QQ_OPENID` 三个环境变量；
   `LEIGOD_TOKEN` 不必预建，面板首次写入时自动创建。

### 2. 构建并启动面板

```bash
git clone https://github.com/Jipai1716/leigod-manager.git
cd leigod-manager

docker build -t leigod-panel:1.1.0 -f panel/Dockerfile .

docker run -d --name leigod-panel --restart unless-stopped \
  -p 5788:5788 \
  -e LEIGOD_QL_BASE_URL=http://<青龙地址>:5700 \
  -e LEIGOD_QL_CLIENT_ID=<client_id> \
  -e LEIGOD_QL_CLIENT_SECRET=<client_secret> \
  -e LEIGOD_TZ=Asia/Shanghai \
  leigod-panel:1.1.0
```

也可以用 compose：把 `panel/docker-compose.yml` 和同目录 `.env` 交给 Docker 或 NAS 的「应用」功能导入。

```text
# .env（不要提交）
LEIGOD_QL_BASE_URL=http://<青龙地址>:5700
LEIGOD_QL_CLIENT_ID=...
LEIGOD_QL_CLIENT_SECRET=...
LEIGOD_TZ=Asia/Shanghai
LEIGOD_PAUSE_TASK_NAME=雷神定时暂停
```

> `LEIGOD_QL_BASE_URL` 必须填**容器能访问到**的地址，不能用 `127.0.0.1`（那是容器自己）。

### 3. 打开面板

浏览器访问 `http://<主机>:5788`，无登录。粘贴 Token 后即可使用。

## 配置项

| 变量 | 默认 | 说明 |
|---|---|---|
| `LEIGOD_QL_BASE_URL` | — | 青龙地址，必填 |
| `LEIGOD_QL_CLIENT_ID` | — | 青龙 API 应用 ID，必填 |
| `LEIGOD_QL_CLIENT_SECRET` | — | 青龙 API 应用密钥，必填 |
| `LEIGOD_TOKEN_ENV` | `LEIGOD_TOKEN` | Token 存放的青龙环境变量名 |
| `LEIGOD_CMDLOG_ENV` | `LEIGOD_CMDLOG` | 事件记录（跨容器共享用） |
| `LEIGOD_PAUSE_STATE_ENV` | `LEIGOD_PAUSE_STATE` | 最近一次暂停结果 |
| `LEIGOD_PAUSE_TASK_NAME` | `雷神定时暂停` | 面板要编辑的青龙任务名 |
| `LEIGOD_TZ` | `Asia/Shanghai` | 时间与日志时区 |
| `LEIGOD_PANEL_PORT` | `5788` | 面板监听端口 |
| `QQ_APP_ID` / `QQ_APP_SECRET` / `QQ_OPENID` | — | QQ 机器人报警（读青龙里同名变量） |

## 浏览器脚本

| 脚本 | 平台 | 能力 |
|---|---|---|
| `tampermonkey/leigod-token.user.js` | 桌面（Tampermonkey） | 复制 Token；一键推送到面板（首次填面板地址，之后记住） |
| `via/leigod-token.user.js` | 手机（Via） | 复制 Token，粘贴到面板 |

两者都只在 `*.leigod.com` 下运行，只读取当前登录态，不碰账号密码、不发任何第三方。

## 定时规则写法

标准 5 段 cron：`分 时 日 月 周`。星期 `0`/`7` = 周日，`1-5` = 工作日，`6` = 周六。

| 需求 | cron |
|---|---|
| 每 6 小时 | `0 */6 * * *` |
| 每天 03:00 | `0 3 * * *` |
| 仅工作日 03:00 | `0 3 * * 1-5` |
| 仅周末 03:00 | `0 3 * * 6,0` |
| 工作日 00:00 与 12:00 | `0 0,12 * * 1-5` |
| 每 2 小时 | `0 */2 * * *` |

保存时会在本地校验（段数、字段范围、字符集，拒绝 `?`），再由青龙的 cron-parser 二次校验，
最后回读比对，确保真的落库。

## 排错

| 现象 | 处理 |
|---|---|
| 面板打不开 | `docker logs leigod-panel`；确认 5788 未被占用 |
| 概览报「青龙接口请求失败」 | `LEIGOD_QL_BASE_URL` 是否容器可达；应用是否具备 `envs` 权限 |
| 写 Token 返回 `401 Access denied` | 青龙应用缺少 `envs` scope |
| 改 cron 返回 400 | 表达式被青龙拒绝，检查段数与取值范围 |
| 改 cron 提示「复核不一致」 | `LEIGOD_PAUSE_TASK_NAME` 与实际任务名不符 |
| 状态一直「未知」 | 看卡片中的原因：未配置 Token / `400006`（Token 被拒）/ 网络失败 |
| 日志查询 `400006` | `account_token` 过期（约 7 天），重新提取后更新 |
| 收不到失败报警 | 检查青龙里的 QQ 三个变量；任务日志里搜「QQ 推送失败」 |

## 安全

- 面板**无鉴权**，请只在内网使用；需要外网访问时请自行加反代与认证。
- Token、API 密钥、QQ 凭据都放在青龙或 `panel.env` 里，不进仓库、不进日志、不回显。
- 面板只读/写固定几个青龙接口，不提供任意命令执行。

## 目录

```
panel/          Web 面板（app.py / Dockerfile / docker-compose.yml）
scripts/        青龙侧脚本（leigod_common.py 公共库 + 各入口）
tampermonkey/   油猴脚本
via/            Via 用户脚本
docs/           接口取证与实现说明
tools/          部署、诊断、回归测试脚本
```

## 已知限制

- `account_token` 约 7 天过期，需手动更新；不做自动刷新。
- 事件记录存在青龙环境变量里（上限 100 条），单人低频使用足够，不适合高并发。
- cron 的中文描述只覆盖常见写法，复杂表达式以青龙实际调度为准。
