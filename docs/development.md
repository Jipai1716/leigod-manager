# 实现与运维说明

面向维护者：代码怎么组织、关键决策为什么这么做、出问题从哪查。
接口细节见 [`api-notes.md`](api-notes.md)。

## 1. 代码结构

| 文件 | 职责 |
|---|---|
| `scripts/leigod_common.py` | 公共库：配置、雷神客户端、青龙客户端、QQ 推送、事件存储、cron 工具 |
| `scripts/leigod_pause.py` | 青龙定时任务入口，**仅失败/未知时推 QQ** |
| `scripts/leigod_{update_token,logs,status,history}.py` | 命令行工具，面板不可用时手工排查 |
| `panel/app.py` | Web 面板（标准库 `http.server` + 内嵌前端） |
| `panel/Dockerfile` | `python:3.11-slim`，无 pip 依赖 |
| `tampermonkey/`、`via/` | 浏览器取 Token 脚本 |

## 2. 面板实现要点

- **零依赖**：只用标准库，镜像里仅 `app.py` + `leigod_common.py`。
- **无鉴权**：按需求去掉访问密码，仅限内网；`/api/*` 直接可用。
- **无状态**：Token、事件、暂停结果、定时规则全部经青龙 OpenAPI 读写，容器可随时重建。
- **健康检查**：`GET /healthz` 返回 200，Dockerfile 与 compose 均配置 HEALTHCHECK。

### 2.1 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/summary` | Token 状态、实时暂停状态、定时规则、最近事件、错误 |
| POST | `/api/token` | 写青龙 Token 变量，不验证有效性 |
| POST | `/api/pause` | 立即暂停；失败时推 QQ |
| GET | `/api/logs?n=3` | 官网最近 N 条暂停记录 |
| GET | `/api/schedule` | 当前 cron + 中文描述 + 预设 |
| POST | `/api/schedule` | 改青龙任务 cron，保存后回读校验 |
| GET | `/api/history?n=20` | 事件记录 |
| GET | `/healthz` | 健康检查 |

### 2.2 暂停状态怎么得到

每次请求 `/api/user/info`，读 `pause_status_id`：`1` → 已暂停，`0` → 未暂停，其它 → 未知。
不缓存、不推断；Token 缺失或接口报错时显示「未知 + 原因」，而不是猜一个状态。

### 2.3 定时规则怎么改

`PUT /open/crons` 需要 `{...commonCronSchema, id}` 的**单个对象**。

实现策略：

1. 本地校验：5 段、字符白名单、各字段范围（分 0-59、时 0-23、日 1-31、月 1-12、周 0-7），拒绝 `?`
2. 取目标任务完整对象，替换 `schedule` 后 PUT；
   若被 Joi 拒绝（未知字段等），退回 `{id, name, command, schedule}` 最小集重试
3. 保存后立刻 GET 回读，与目标 cron 比对，不一致就报错——**不把「请求成功」当「保存成功」**

预设见 `cron_presets()`：

| 预设 | cron |
|---|---|
| 每 6 小时 | `0 */6 * * *` |
| 每天 03:00 | `0 3 * * *` |
| 工作日 03:00 | `0 3 * * 1-5` |
| 休息日 03:00 | `0 3 * * 6,0` |
| 工作日 00:00 与 12:00 | `0 0,12 * * 1-5` |
| 每 2 小时 | `0 */2 * * *` |

## 3. 部署

```bash
docker build -t leigod-panel:1.1.0 -f panel/Dockerfile .
docker run -d --name leigod-panel --restart unless-stopped -p 5788:5788 \
  -e LEIGOD_QL_BASE_URL=http://<qinglong>:5700 \
  -e LEIGOD_QL_CLIENT_ID=<id> \
  -e LEIGOD_QL_CLIENT_SECRET=<secret> \
  leigod-panel:1.1.0
```

`tools/deploy_panel.sh` 是一个可直接复用的参考实现：自动探测宿主局域网 IP
（排除 `172.x` 容器网段）生成 `panel.env`（600）、构建镜像、启动容器并做健康检查。

青龙侧脚本放到 `/ql/data/scripts/leigod/`，定时任务命令写 `task leigod/leigod_pause.py`——
用 `task` 而不是裸 `python3`，因为前者会注入面板里的环境变量。

## 4. 青龙侧准备

1. 新建 API 应用，勾选 `envs`、`crons`，记下 `client_id` / `client_secret`。
2. 需要的环境变量（面板只需要读青龙地址与凭据，Token 由面板写入）：

   | 变量 | 用途 |
   |---|---|
   | `LEIGOD_TOKEN` | Token 存放处，面板首次写入时自动创建 |
   | `LEIGOD_CMDLOG` | 事件记录（JSON 数组，上限 100 条） |
   | `LEIGOD_PAUSE_STATE` | 最近一次暂停结果 |
   | `QQ_APP_ID` / `QQ_APP_SECRET` / `QQ_OPENID` | 失败报警 |

3. 定时任务：`雷神定时暂停` → `task leigod/leigod_pause.py`，cron 由面板管理。

> 若应用 scope 改过却不生效：`Apps` 表与 `keyv.sqlite` 的 `keyv:apps` 缓存是两份数据，
> 都要更新（或重启青龙让缓存重建），否则一直 401。

## 5. 状态与事件模型

- **Token**：青龙环境变量（默认 `LEIGOD_TOKEN`）
- **事件**：`LEIGOD_CMDLOG`，JSON 数组，最多 100 条
- **暂停结果**：`LEIGOD_PAUSE_STATE`

事件字段：

```json
{"ts": 1792..., "time": "2026-10-17 23:31:16", "op": "pause_result",
 "op_label": "暂停任务结果", "result": "失败", "detail": "..."}
```

`op`：`token_update` / `pause_trigger` / `pause_result` / `logs_query` / `error`。

为什么把事件放环境变量：多个容器之间没有共享挂载，青龙环境变量是唯一既公共又可写的位置。
代价是不适合高并发写入，单人低频使用足够。

## 6. 测试记录

面板 v1.1 回归（`tools/test_panel_v11.py`，在容器内跑）11/11 通过：

| 用例 | 结果 |
|---|---|
| 无登录访问 `/api/summary` | 200 |
| 实时暂停状态 | 返回 `state` + `pause_status_id`，与官网一致 |
| 读取当前 cron | 返回表达式与中文描述 |
| 非法 cron `0 99 * * *` | 本地拦截「时字段超出范围 0-23」 |
| 段数不足 / 含 `?` | 本地拦截并说明原因 |
| 保存工作日规则 `0 3 * * 1-5` | 成功，回读一致 |
| 恢复默认规则 | 成功 |
| 官网时长日志 | 真实返回记录（暂停时间/恢复时间/状态码） |
| 历史记录 | 返回记录列表 |

其他已验证项：

- 写 Token 返回「写入结果：成功 / 有效性验证：未执行」；空 Token 被拒
- 用无效 Token 查询时，官网返回 `400006`，面板原样报错，不伪造数据
- 容器 HEALTHCHECK 通过（`/healthz` 200）

未覆盖：账号处于未暂停状态时的真实暂停动作、QQ 失败报警的真实投递。

## 7. 回滚

```bash
docker rm -f leigod-panel
rm -rf <配置目录>            # panel.env 等
rm -rf /ql/data/scripts/leigod
# 青龙后台删除定时任务「雷神定时暂停」，并清理新增的 LEIGOD_* 环境变量
```

面板完全独立，删除不影响青龙上的其它任务。

## 8. 排错顺序

1. `docker logs leigod-panel` 看启动与请求日志
2. 面板概览里「最近错误」一行
3. `docker exec leigod-panel python3 -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:5788/api/summary').read()[:400])"`
4. 青龙侧：任务日志、`LEIGOD_PAUSE_STATE` 的 detail
5. 官网接口：直接 POST `/api/user/info` 看 `code`（`400006` = Token 失效）

## 9. 设计取舍

### 9.1 为什么不做 QQ 指令入口

最初实现过「QQ 私聊发指令 → 机器人插件 → 执行」，实际跑下来发现入站链路有三处容易踩：

1. 消息框架的平台适配器常见默认关闭，插件加载成功也收不到消息；
2. 适配器里存的 AppSecret 可能是旧值，报 `100016 invalid appid or secret`；
3. 框架自身的 ID 白名单为空且开关打开时，会静默拦掉所有人。

即使修通，入口也依赖一个跑着其它重型插件的容器，任何配置变更或重启都可能带挂。
权衡后改为 Web 面板：入口只依赖一个几十 MB 的自包含容器，失败面小，且顺带满足
「只在失败时报警」的需求（不需要日报推送）。

### 9.2 为什么事件不落文件

青龙与面板是两个容器，无共享挂载。让它们都能读写的只有青龙环境变量。
如果以后允许改挂载，可以换成共享目录 + JSONL，吞吐会好很多。

### 9.3 为什么不用 requests

青龙镜像与 `python:3.11-slim` 都能装 `requests`，但标准库 `urllib` 足够，
少一个依赖就少一处镜像变大与版本冲突的可能。
