# 接口取证笔记

本文记录项目依赖的外部接口是怎么确认的，方便上游变更时快速比对。
所有结论都来自实际请求或官方前端代码，没有推测成分。

## 1. 雷神官网接口

Base：`https://webapi.leigod.com`

### 1.1 证据来源

官网 `vip.leigod.com` 的前端 bundle（未压缩源码里能直接看到路径常量与签名函数）：

- `/js/chunk-common.js` — 全部 URL 常量、HTTP 客户端、`sign()` 实现
- `/js/user.js` — 暂停页逻辑，调用暂停记录接口

关键片段（压缩后原样）：

```js
e.URL_USER_INFO     = "/api/user/info"
e.URL_USER_PAUSE    = "/api/user/pause"
e.URL_USER_RECOVER  = "/api/user/recover"
e.URL_USER_PAUSELOG = "/api/user/pause/lists"
```

暂停页调用方式：

```js
e = URL_USER_PAUSELOG
a.account_token = token
a.size = 15
this.http.post(e, a)
```

### 1.2 通用请求约定

- POST JSON，body 自动附加 `lang`、`os_type=4`
- 只有带 `isSign` 的接口才需要 `ts` + `sign`
- 成功码 `0`；Token 失效 `400006`；未付费 `400877`

### 1.3 签名算法

bundle 里 key 是硬编码的，算法为：

```text
ts   = floor(now / 1000)
raw  = "k1=v1&k2=v2&...&key=<HARDCODED_KEY>"   // 值为原始串，不做 urlencode
sign = md5(raw)
```

本项目只用到**不需要签名**的接口（`info` / `pause` / `recover` / `pause/lists`），
签名实现仍保留在 `leigod_common.sign_params()` 里，供将来登录场景使用。

### 1.4 端点清单

| 用途 | 方法 | 路径 | 参数 | 需签名 |
|---|---|---|---|---|
| 用户信息 | POST | `/api/user/info` | `account_token`, `lang` | 否 |
| 暂停 | POST | `/api/user/pause` | `account_token`, `lang` | 否 |
| 恢复 | POST | `/api/user/recover` | `account_token`, `lang` | 否 |
| 暂停记录 | POST | `/api/user/pause/lists` | `account_token`, `size` | 否 |
| 密码登录 | POST | `/api/auth/login/v1` | `country_code`,`username`,`password(md5)`,`src_channel` | 是 |
| 短信验证码 | POST | `/tools/smscode` | `phone`,`country_code`,`state`,`checkcode` | 否 |

> 登录接口已加极验 v4 验证码，无法纯脚本登录；本项目因此不实现登录，只消费 `account_token`。

### 1.5 实测响应结构

`POST /api/user/info` 关键字段：

```json
{"pause_status_id": 1}
```

`1` = 已暂停，`0` = 未暂停。（同响应里的 `nickname`/`mobile` 已被官网脱敏。）

`POST /api/user/pause/lists`：

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

- `data` 是数组，字段：`id` / `status` / `pause_time` / `resume_time` / `op_source`
- 时间是 `"YYYY-MM-DD HH:MM:SS"` 字符串，不是时间戳
- `resume_time` 为 `null` 表示尚未恢复

### 1.6 Token 从哪来

`localStorage.account_token` 存的是一个 JSON，取其中的 `account_token` 字段：

```js
JSON.parse(localStorage.getItem('account_token')).account_token
```

有效期约 7 天。浏览器脚本会额外做容错：对象/字符串/`data` 嵌套/全 key 扫描。

## 2. 青龙面板 OpenAPI

以下基于 **2.21.0-16** 验证，版本差异请重新核对。

### 2.1 路径与鉴权

- 对外前缀 `/open/*`，服务端内部重写到 `/api/*`
- 鉴权不是常见的 `POST {appKey, appSecret}`，而是：

```text
GET /open/auth/token?client_id=<id>&client_secret=<secret>
→ {"code":200,"data":{"token":"...","expiration":<epoch>}}
```

- 后续请求带 `Authorization: Bearer <token>`

### 2.2 权限（scope）

应用需要按用途勾选：读写环境变量要 `envs`，读写定时任务要 `crons`。
缺 scope 时返回 `401 {"code":401,"message":"Access denied"}`。

scope 配置存在 `Apps` 表，同时被缓存在 `keyv.sqlite` 的 `keyv:apps` 键里；
只改数据库不改缓存不会生效。

### 2.3 常用端点

| 用途 | 方法 | 路径 | 备注 |
|---|---|---|---|
| 鉴权 | GET | `/open/auth/token` | query 传 `client_id` / `client_secret` |
| 环境变量列表 | GET | `/open/envs` | 返回数组，含 `id`/`name`/`value` |
| 新建变量 | POST | `/open/envs` | body 是**数组** |
| 更新变量 | PUT | `/open/envs` | body 是**对象**，需带 `id` |
| 删除变量 | DELETE | `/open/envs` | body 是 id 数组 |
| 任务列表 | GET | `/open/crons` | 注意 `data` 是 `{data:[...], total:N}` 的包装 |
| 新建任务 | POST | `/open/crons` | body 是对象 |
| 更新任务 | PUT | `/open/crons` | body 是**单个对象**，需带 `id`，不是数组 |
| 删除任务 | DELETE | `/open/crons` | body 是 id 数组 |

### 2.4 cron 校验

服务端用 `cron-parser` 校验，另外显式拒绝：

- `?`（Quartz 语法，node-schedule 不认）
- 裸 `/N`（如 `5 /10 * * *`）

非法时返回 `400 Bad Request`。

## 3. QQ 机器人 OpenAPI

推送契约（C2C 主动消息）：

```text
POST https://bots.qq.com/app/getAppAccessToken
  {"appId": "...", "clientSecret": "..."}  → {"access_token": "..."}

POST https://api.sgroup.qq.com/v2/users/{openid}/messages
  Header: Authorization: QQBot <access_token>
  markdown: {"msg_type": 2, "markdown": {"content": "..."}, "msg_seq": <N>}
  纯文本  : {"content": "...", "msg_type": 0}
```

markdown 通道失败时自动降级纯文本（本项目默认用纯文本，失败报警不需要排版）。

注意：官方 Bot API 没有「拉取历史消息」的接口，收消息需要 WebSocket 或 webhook，
因此本项目**不做入站指令**，控制入口是 Web 面板。
