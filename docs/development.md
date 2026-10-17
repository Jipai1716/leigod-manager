# 实现与运维说明

> 架构已从「QQ 固定指令」改为「Docker Web 面板」，理由见 §9。

## 1. 代码结构

| 文件 | 职责 |
|---|---|
| `scripts/leigod_common.py` | 公共库：配置、雷神客户端、青龙客户端、QQ 推送、事件存储、业务动作 |
| `scripts/leigod_pause.py` | 青龙任务 14 的入口，**仅失败/未知时推 QQ** |
| `scripts/leigod_{update_token,logs,status,history}.py` | 命令行工具（面板不可用时手工排查） |
| `panel/app.py` | Web 面板（标准库 http.server + 内嵌前端） |
| `panel/Dockerfile` | `python:3.11-slim`，无 pip 依赖 |
| `via/leigod-token.user.js` | Via 用户脚本 |

## 2. 面板实现要点

- **无第三方依赖**：`http.server.ThreadingHTTPServer` + 内嵌 HTML/JS，镜像里只有 `app.py` 和 `leigod_common.py`。
- **无鉴权**：按需求去掉访问密码，仅限局域网；`/api/*` 直接可用。
- **无状态**：Token、事件、暂停结果、定时规则全部通过青龙 OpenAPI 读写，容器不挂卷，删了重建不丢数据。
- **健康检查**：`GET /healthz` 返回 200，Dockerfile 与 compose 都配了 HEALTHCHECK。

接口：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/summary` | 概览：Token 状态、**实时暂停状态**、定时规则、最近事件、错误 |
| POST | `/api/token` | `{token}` → 写入青龙 `LEIGOD_TOKEN`，不验证有效性 |
| POST | `/api/pause` | 立即暂停；失败时顺带推 QQ |
| GET | `/api/logs?n=3` | 官网最近 N 条暂停记录 |
| GET | `/api/schedule` | 当前 cron + 中文描述 + 预设 |
| POST | `/api/schedule` | `{cron}` → 改青龙任务 cron，**保存后回读校验** |
| GET | `/api/history?n=20` | 本地事件记录 |
| GET | `/healthz` | 健康检查 |

### 2.1 暂停状态怎么来的

`/api/user/info` 的 `pause_status_id`：`1` → 已暂停，`0` → 未暂停，其它 → 未知。
面板每次都实时问官网，不吃缓存、不做推断；Token 缺失或接口报错时明确显示「未知 + 原因」。

### 2.2 定时规则怎么改的

`PUT /open/crons` 需要 `{...commonCronSchema, id}` 的**单个对象**（不是数组）。
实现先按完整字段提交，若被 Joi 校验拒绝则退回到 `{id, name, command, schedule}` 最小集；
保存后立刻 `GET /open/crons` 回读比对，不一致就报错。

本地先做一层校验：5 段、字符白名单、各字段数值范围（分 0-59、时 0-23、日 1-31、月 1-12、周 0-7），
拒绝 `?`（Quartz 语法，node-schedule 不认）。青龙服务端还会用 cron-parser 再校验一次。

预设（`cron_presets()`）：

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
tar -czf leigod.tgz -C leigod-manager panel scripts
scp leigod.tgz jipai@<NAS>:/tmp/
ssh jipai@<NAS> 'mkdir -p /tmp/leigod-deploy2 && tar -xzf /tmp/leigod.tgz -C /tmp/leigod-deploy2'
ssh jipai@<NAS> 'NAS_SUDO_PW=... bash /tmp/deploy_panel.sh'   # 构建 + 启动
```

`deploy_panel.sh` 首次运行会生成 `panel.env`（600），其中 `LEIGOD_QL_BASE_URL` 由脚本自动探测
宿主局域网 IP（排除 `172.x` 容器网段）。重复运行会复用该文件。

```text
LEIGOD_QL_BASE_URL=http://<NAS_IP>:5700
LEIGOD_QL_CLIENT_ID=...
LEIGOD_QL_CLIENT_SECRET=...
LEIGOD_TZ=Asia/Shanghai
LEIGOD_PAUSE_TASK_NAME=雷神定时暂停
```

更新代码后重跑 `deploy_panel.sh` 即可（重建镜像并重启容器）。

## 4. 青龙侧准备（已执行，重装参考）

1. `system` 应用补 `envs` scope —— `Apps` 表 + `keyv.sqlite` 的 `keyv:apps` 缓存都要改，
   否则永久 401（`tools/fix_scope.sh`、`tools/fix_keyv.sh`）。
2. 配置变量：`LEIGOD_QL_BASE_URL`、`LEIGOD_QL_CLIENT_ID`、`LEIGOD_QL_CLIENT_SECRET`、`LEIGOD_TZ`。
3. 建定时任务 `雷神定时暂停`（`tools/create_crons.sh`）。
4. 青龙侧脚本部署到 `/vol1/1000/Docker/qinglong/scripts/leigod`（`tools/deploy.sh`）。

## 5. 状态与事件模型

- Token：青龙环境变量 `LEIGOD_TOKEN`（面板写入）。
- 事件：`LEIGOD_CMDLOG`（JSON 数组，最多 100 条），面板与青龙任务共用。
- 暂停结果：`LEIGOD_PAUSE_STATE`。

`op` 取值：`token_update` / `pause_trigger` / `pause_result` / `logs_query` / `error`。

## 6. 测试记录

面板 v1.1（无密码版），`tools/test_panel_v11.py`，11/11 通过：

| 测试 | 结果 |
|---|---|
| 无登录直接访问 `/api/summary` | 200 |
| 实时暂停状态 | `state=paused, pause_status_id=1`（账号当时确实处于暂停） |
| 读取当前 cron | `0 */6 * * *`，描述「整点，每 6 小时，每天」 |
| 非法 cron（`0 99 * * *`） | 被青龙 400 拒绝，未落库 |
| 段数不足 / 含 `?` | 本地拦截并给出原因 |
| 保存工作日规则 `0 3 * * 1-5` | 成功，回读一致，描述「整点，在 03:00，仅工作日」 |
| 恢复默认规则 | 成功 |
| 官网时长日志 | **真实返回 3 条**：`暂停时间：2026-10-17 23:12:38` 等 |
| 历史记录 | 返回 5 条 |

早前已验证：写 Token（含「有效期未执行」声明）、空 Token 拒绝、假 Token 查询返回官网
真实错误码 `400006`（不伪造数据）、容器 HEALTHCHECK 通过。

未覆盖：真实 Token 下的「暂停动作」端到端（账号当前已处于暂停态，接口会走「已暂停不重复调用」分支）；
QQ 失败报警的真实推送。

## 7. 回滚

```bash
# 停面板
sudo docker rm -f leigod-panel
sudo rm -rf /vol1/1000/Docker/leigod-panel

# 删定时任务 14（青龙后台或 DELETE /open/crons body [14]）
# 删青龙侧脚本
sudo rm -rf /vol1/1000/Docker/qinglong/scripts/leigod
# 删新增环境变量 LEIGOD_*
```

原有 5 个任务与 `QQ_APP_ID` 等变量不受影响。

## 8. 排错

| 现象 | 检查 |
|---|---|
| 面板打不开 | `docker ps \| grep leigod-panel`；`docker logs leigod-panel`；端口 5788 是否被占 |
| 暂停状态显示「未知」 | 看卡片里的原因：未配置 Token / Token 被拒（400006）/ 网络失败 |
| 概览报「青龙接口请求失败」 | `LEIGOD_QL_BASE_URL` 必须是容器能访问的局域网 IP，不能写 127.0.0.1 |
| 改 cron 报 400 | 青龙用 cron-parser 校验；检查段数、范围、是否含 `?` |
| 改 cron 提示「复核不一致」 | 任务名对不上（`LEIGOD_PAUSE_TASK_NAME`）或任务被改名 |
| 写 Token 报 401 Access denied | 青龙应用缺 `envs` scope（见 §4.1）；改 cron 还需要 `crons` scope |
| 查日志报 400006 | Token 过期，重新提取后在面板更新 |
| 暂停一直「未知」 | 调接口后复查 `pause_status_id` 仍不是 1；看 `LEIGOD_PAUSE_STATE` 的 detail |
| 没收到失败报警 | 青龙 `QQ_APP_ID/SECRET/OPENID` 是否有效；任务日志里看「QQ 推送失败」 |

## 9. 为什么放弃 QQ 指令方案

最初按「QQ 私聊发 `/l u <Token>`」实现，AstrBot 插件写好也加载成功了，但实测发现：

1. AstrBot 三个平台适配器默认全部 `enable: false`，从未接收过任何消息；
2. 启用 `qq_official` 后报 `100016 invalid appid or secret`（存的 secret 是旧的）；
3. `platform_settings.id_whitelist` 为空且白名单开关开启，会拦截所有人。

三层修完后链路能通，但**入站依赖 AstrBot 的运行状态**，而 AstrBot 平时还在跑 LLM 插件，
任何一次配置变更或重启都可能把指令入口带挂。权衡后改为 Web 面板：入口只依赖一个
几十 MB 的自包含容器，失败面小得多，也顺手去掉了日报推送（按需求只保留失败报警）。

相关废弃代码已删除，排查过程保留在 `tools/revert_astrbot.py`、
`tools/cleanup_cmd_system.sh` 里。
