# 环境与接口调查记录（阶段一产出）

调查时间：2026-10-17
调查方式：SSH 登录 NAS（`jipai@<NAS_LAN_IP>`，Debian 12，主机名 `JipaiNas`）逐项取证；雷神接口证据来自官网前端 bundle。
结论分三类：**已确认**（有命令输出或源码为证）、**需外部输入**（必须你提供才能继续）、**不成立**（原始文档假设与实际不符）。

---

## 1. 容器与服务现状（已确认）

| 容器 | 镜像 | 状态 | 端口 |
|---|---|---|---|
| `qinglong` | `whyour/qinglong:latest` | Up 36h (healthy) | 5700 |
| `astrbot` | `soulter/astrbot:latest` | Up 36h | 6185 / 8844 / 8899 / 8898 |
| `ani-rss` | `fnapp/wushuo894_ani-rss` | Up | 17789 |
| `launcher` | `natfrp.com/launcher` | Up（内网穿透） | — |
| `napcat` / `napcat2` | `lmq8267/napcat` | **Exited** | — |

Docker 版本 28.5.2。`jipai` 用户不在 docker 组，所有 docker 操作需 `sudo`。
宿主 `/vol1/1000/Docker/docker-compose.yml` 只定义了 `luker`，**AstrBot 与青龙由 NAS 应用中心托管**，不能靠 compose 重建 —— 这条决定了后面的架构（见 §6）。

## 2. 青龙面板（已确认）

- 版本 `2.21.0-16`，容器内 Python `3.11.15`，`requests 2.34.2`，自带 `ql` CLI（`/usr/local/bin/ql`）。
- 宿主机挂载：`/vol1/1000/Docker/qinglong` → 容器 `/ql/data`。
- 数据库：`/ql/data/db/database.sqlite`，表含 `Crontabs`、`Envs`、`Apps`、`Logs` 等。
- 已存在 API 应用：`system`，`client_id = <QL_CLIENT_ID>`。

### 现有定时任务（全部保留，不修改）

| ID | 名称 | 脚本 | cron |
|---|---|---|---|
| 1 | 济南天气播报 | `weather_jinan.py` | `30 7 * * *` |
| 2 | 必应积分助手 | `bing_rewards.py` | `20 8 * * *` |
| 4 | 必应积分助手2 | `bing_rewards2.py` | `40 8 * * *` |
| 5 | qB下载日报 | `qbt_report.py` | `0 18 * * *` |
| 6 | qB下载快照 | `qbt_report.py --scan-only` | `30 */2 * * *` |

### 现有环境变量（值未读取、未记录）

`QQ_APP_ID`、`QQ_APP_SECRET`、`QQ_OPENID`、`BING_COOKIE`、`BING_COOKIE2`、`QBT_ALWAYS`。

## 3. 与开发文档不一致的地方（重要）

### 3.1 不存在「现有雷神暂停任务」——不成立

全盘检索 `leigod` / `雷神`：

- 青龙容器内 `/ql/data/scripts`：零命中
- 青龙 `Envs` 表的名称与值：零命中
- 宿主机 `/vol1/1000/Docker`、`/home`、`/root`：零命中

结论：文档 §6「保留现有定时暂停任务、不重写已可用逻辑」没有可保留的对象。
**处理**：按你的选择，新建一个独立暂停任务（第 6 个），现有 5 个任务的脚本、cron、变量一个都不动。

### 3.2 不存在既有「雷神 Token 环境变量」——不成立

同理，没有可复用的变量名。**处理**：新建 `LEIGOD_TOKEN`，并让新暂停任务与指令入口共用同一变量名（单一来源）。

### 3.3 现有 QQ 机制是纯单向推送——部分不成立

青龙 → 脚本 → `api.sgroup.qq.com` → 用户，只能出不能进；QQ 官方 Bot API 没有「拉取历史消息」接口。
**处理**：按你的选择，用已运行的 AstrBot（4.26.8）写固定指令插件作为入站入口，不新增容器。

## 4. QQ 机器人推送契约（已确认，取自 `weather_jinan.py`）

```text
POST https://bots.qq.com/app/getAppAccessToken
  {"appId": QQ_APP_ID, "clientSecret": QQ_APP_SECRET}      -> {"access_token": "..."}

POST https://api.sgroup.qq.com/v2/users/{openid}/messages
  Header: Authorization: QQBot <access_token>
  markdown: {"msg_type": 2, "markdown": {"content": "..."}, "msg_seq": <N>}
  纯文本  : {"content": "...", "msg_type": 0}
```

markdown 失败会自动降级纯文本 —— 本项目沿用该范式。

## 5. 雷神官网接口（已确认，证据来自官网前端 bundle）

来源：`https://vip.leigod.com/js/chunk-common.js`、`user.js`（已落盘 `refs/web/`）。

### 5.1 Base URL 与请求约定

- Base：`https://webapi.leigod.com`
- 所有请求自动附加 `lang`、`os_type=4`
- 需要签名的接口才会附加 `ts` + `sign`

### 5.2 签名算法（bundle 内 `e.sign`，key 硬编码）

```js
ts   = floor(now/1000)
obj  = {ts, ...body}          // 排序后拼接
raw  = "k1=v1&k2=v2&...&key=5C5A639C20665313622F51E93E3F2783"   // 值不做 urlencode
sign = md5(raw)
```

### 5.3 端点清单

| 用途 | 方法 | 路径 | 参数 | 需签名 |
|---|---|---|---|---|
| 用户信息 | POST | `/api/user/info` | `account_token`, `lang` | 否 |
| 暂停 | POST | `/api/user/pause` | `account_token`, `lang` | 否 |
| 恢复 | POST | `/api/user/recover` | `account_token`, `lang` | 否 |
| **暂停记录（时长日志）** | POST | `/api/user/pause/lists` | `account_token`, `size` | 否 |
| 密码登录 | POST | `/api/auth/login/v1` | `country_code`,`username`,`password(md5)`,`src_channel` | **是** |
| 短信验证码 | POST | `/tools/smscode` | `phone`,`country_code`,`state`,`checkcode` 等 | 否 |
| 发送短信 | POST | `/tools/smscode/send` | `mobile_num`,`country_code` | 否 |

关键证据（`user.js`，暂停页调用）：

```js
e = URL_USER_PAUSELOG            // "/api/user/pause/lists"
a = new R.G
a.account_token = token
a.size = 15
this.http.post(e, a)
```

成功码 `0`；Token 失效码 `400006`；未付费 `400877`。

### 5.4 Token 提取方式（已确认）

第三方实现与官网一致：`localStorage.account_token` 为 JSON，取 `.account_token` 字段；有效期约 7 天。
本项目 Via 脚本已按此实现，并额外做全量 key 扫描与结构容错。

### 5.5 实测确认（2026-10-17，有效 Token）

`POST /api/user/pause/lists` 的响应结构：

```json
{
  "code": 0,
  "msg": "...",
  "ts": 1792...,
  "data": [
    {"id": 1950995083, "status": 1, "pause_time": "2026-10-17 23:12:38",
     "resume_time": null, "op_source": 0}
  ]
}
```

- `data` 是**数组**，元素字段：`id` / `status` / `pause_time` / `resume_time` / `op_source`
- `pause_time`、`resume_time` 是 `"YYYY-MM-DD HH:MM:SS"` 字符串（不是时间戳）
- `resume_time` 为 `null` 表示尚未恢复
- 响应自带 `ts`；记录按 `pause_time` 倒序可用，本项目仍本地排序后取前 3

`POST /api/user/info` 里 `pause_status_id`：`1` = 已暂停，`0` = 未暂停；实测同一账号返回的
`nickname`/`mobile` 已被官网脱敏（如 `156****8959`）。

## 6. 架构决策（基于上述事实）

| 问题 | 决策 | 理由 |
|---|---|---|
| 没有共享挂载 | 事件日志放青龙环境变量 `LEIGOD_CMDLOG`（JSON 数组，上限 100 条） | AstrBot 与青龙由应用中心托管，改挂载需重建容器，违反「不新增/少改动」约束 |
| 暂停逻辑归属 | 单一实现 `leigod_common.do_pause()`，青龙 cron 与 AstrBot 指令共用 | 不复制暂停逻辑；手动触发与定时执行行为完全一致 |
| 手动触发方式 | 指令入口内直接调用同一函数（不走青龙「运任务」API） | 原文档的前提是有现成任务可触发，实际没有；复用同一函数更等价且可拿到真实结果 |
| 代码分发 | 青龙侧 `scripts/` + 插件目录内 vendored 副本，由 `deploy.sh` 同步 | 两容器无共享卷，靠部署脚本保证同源 |

## 7. 待你提供

| 项 | 用途 | 状态 |
|---|---|---|
| 雷神 `account_token` 或其对应的短信验证码 | 实测 `pause/lists` 响应字段、跑通日志查询 | **待提供** |
| 允许执行指令的 QQ openid | 写入 `LEIGOD_ALLOWED_IDS` | **待提供**（可先用 `QQ_OPENID` 试） |
| 青龙 API 应用 secret | 指令入口读写环境变量 | 可从库中读取，需你确认是否复用 `system` 应用 |
