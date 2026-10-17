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
- **鉴权**：密码登录，Cookie 为 `HMAC-SHA256(password, ts)`，有效期 7 天；`/api/*` 未登录返回 401 JSON。
- **无状态**：Token、事件、暂停结果全部通过青龙 OpenAPI 读写，容器不挂卷，删了重建不丢数据。
- **健康检查**：`GET /healthz` 返回 200，Dockerfile 与 compose 都配了 HEALTHCHECK。

接口：

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/login` | `{password}` → 设 Cookie |
| GET | `/api/summary` | 概览（Token 状态、最近暂停、最近日志、错误） |
| POST | `/api/token` | `{token}` → 写入青龙 `LEIGOD_TOKEN`，不验证有效性 |
| POST | `/api/pause` | 立即暂停；失败时顺带推 QQ |
| GET | `/api/logs?n=3` | 官网最近 N 条时长日志 |
| GET | `/api/history?n=20` | 本地事件记录 |
| GET | `/healthz` | 健康检查 |

## 3. 部署

```bash
tar -czf leigod.tgz -C leigod-manager panel scripts
scp leigod.tgz jipai@<NAS>:/tmp/
ssh jipai@<NAS> 'mkdir -p /tmp/leigod-deploy2 && tar -xzf /tmp/leigod.tgz -C /tmp/leigod-deploy2'
ssh jipai@<NAS> 'NAS_SUDO_PW=... bash /tmp/deploy_panel.sh'   # 构建 + 启动
```

`deploy_panel.sh` 首次运行会生成密码（输出 `PINNED_PASSWORD:...`），写入
`/vol1/1000/Docker/leigod-panel/panel.env`（600）。重复运行会复用该文件。

更新代码后重跑 `deploy_panel.sh` 即可（会重建镜像并重启容器）。

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

| 测试 | 方式 | 结果 |
|---|---|---|
| 未登录访问 API | `GET /api/summary` 无 Cookie | 401 |
| 错误密码 | `POST /api/login` | 401 |
| 正确密码登录 | 读 `panel.env` 密码 | 200 + `lg_sid` Cookie |
| 写入 Token | `POST /api/token` | 成功，回复含「有效性验证：未执行」 |
| 概览状态同步 | `GET /api/summary` | 已配置、长度正确 |
| 空 Token | `POST /api/token` `"   "` | 拒绝 |
| 假 Token 查日志 | `GET /api/logs` | 官网真实返回 `400006`，面板原样报错不伪造 |
| 历史记录 | `GET /api/history` | 返回 3 条 |
| 页面渲染 | `GET /` | 200，6898 字节 |
| 未配置 Token 时暂停 | `task leigod/leigod_pause.py --no-push` | 退出码 2，提示先配置 Token |
| **真实 Token 下的暂停与日志** | 需要有效 Token | **未测** |
| **QQ 失败报警** | 需要一次真实失败 | **未测**（逻辑已接好） |

一键回归：`tools/test_panel_api.py`（在容器内跑，需 `LEIGOD_PANEL_PASSWORD`）。

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
| 登录一直失败 | `panel.env` 里的 `LEIGOD_PANEL_PASSWORD` 是否与输入一致（改完要重启容器） |
| 概览报「青龙接口请求失败」 | `LEIGOD_QL_BASE_URL` 必须是容器能访问的局域网 IP，不能写 127.0.0.1 |
| 写 Token 报 401 Access denied | 青龙应用缺 `envs` scope（见 §4.1） |
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
