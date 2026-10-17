# 实现与运维说明

## 1. 代码结构

| 文件 | 职责 |
|---|---|
| `scripts/leigod_common.py` | 公共库：配置、雷神客户端、青龙客户端、QQ 推送、事件存储、业务动作 |
| `scripts/leigod_cmd.py` | 固定指令解析与分发；`--selftest` 可离线验证 |
| `scripts/leigod_pause.py` | 青龙任务 14 的入口 |
| `scripts/leigod_daily_report.py` | 青龙任务 15 的入口 |
| `scripts/leigod_{update_token,logs,status,history}.py` | 手工/调试入口 |
| `astrbot_plugin_leigod_manager/main.py` | AstrBot 入站指令插件 |
| `via/leigod-token.user.js` | Via 用户脚本 |

插件目录里 `lib/` 是公共库的副本（两容器无共享挂载），由 `deploy.sh` 同步，保证同源。

## 2. 部署步骤

```bash
# 本机打包
tar -czf leigod-deploy.tgz scripts astrbot_plugin_leigod_manager via docs
scp leigod-deploy.tgz jipai@<NAS>:/tmp/
ssh jipai@<NAS> 'mkdir -p /tmp/leigod-deploy && tar -xzf /tmp/leigod-deploy.tgz -C /tmp/leigod-deploy'

# 服务器端
ssh jipai@<NAS> 'sudo bash /tmp/leigod-deploy/deploy.sh --restart-astrbot'
```

`deploy.sh` 做的事：

1. 复制脚本到 `/vol1/1000/Docker/qinglong/scripts/leigod`（容器内 `/ql/data/scripts/leigod`）
2. 复制插件到 `/vol1/1000/Docker/astrbot/data/plugins/astrbot_plugin_leigod_manager`
3. 把公共库同步进插件 `lib/`
4. 修权限（`chmod a+rX`，state 目录 777）
5. 容器内可见性检查
6. 可选重启 AstrBot

## 3. 首次配置（已在本机执行过，重装时参考）

1. 青龙「应用设置」里的 `system` 应用补上 `envs` scope：

   ```sql
   -- Apps 表
   update Apps set scopes='["crons","system","dashboard","envs"]' where name='system';
   -- 同时改 keyv.sqlite 里的 keyv:apps 缓存，否则不生效
   ```

   本项目是用 python 直接改的 DB + `keyv`（见提交记录），**不需要重启青龙**。

2. 写入配置项（青龙环境变量）：`LEIGOD_QL_BASE_URL`、`LEIGOD_QL_CLIENT_ID`、
   `LEIGOD_QL_CLIENT_SECRET`、`LEIGOD_ALLOWED_IDS`、`LEIGOD_TZ`。

3. 生成插件配置 `config.json`（含青龙凭据，权限 600）：

   ```json
   {
     "ql_base": "http://<NAS_IP>:5700",
     "ql_client_id": "...",
     "ql_client_secret": "...",
     "token_env": "LEIGOD_TOKEN",
     "allowed_ids": ["<你的 openid>"],
     "tz": "Asia/Shanghai",
     "state_dir": "/AstrBot/data/plugins/astrbot_plugin_leigod_manager/state"
   }
   ```

   注意 `ql_base` 必须是 AstrBot 容器能访问到的地址（用 NAS 的局域网 IP，不能用 127.0.0.1）。

4. 建两个定时任务（已建，id 14 / 15）：

   | id | 名称 | 命令 | cron |
   |---|---|---|---|
   | 14 | 雷神定时暂停 | `task leigod/leigod_pause.py` | `0 */6 * * *` |
   | 15 | 雷神每日日报 | `task leigod/leigod_daily_report.py` | `59 23 * * *` |

   改频率只改这两个任务的 cron，不要碰原有 5 个任务。

## 4. 关键接口（证据见 `docs/env-survey.md`）

```python
# 暂停
LeigodClient(token).pause()
# 状态
LeigodClient(token).is_paused()          # pause_status_id == "1"
# 时长日志
LeigodClient(token).pause_logs(size=15)  # POST /api/user/pause/lists
```

- 成功码 `0`，Token 失效码 `400006`（映射成「被官网拒绝」，不推测具体原因）。
- 签名算法：`md5("k=v&...&key=<硬编码>")`，值不做 urlencode；本项目的只读与暂停接口均**不需要**签名。

## 5. 状态与事件模型

事件日志（`LEIGOD_CMDLOG`，JSON 数组，最多 100 条）：

```json
{"ts":1792..., "time":"2026-10-17 19:31:16", "op":"pause_result",
 "op_label":"暂停任务结果", "result":"失败", "detail":"未配置 Token"}
```

`op` 取值：`token_update` / `pause_trigger` / `pause_result` / `logs_query` / `daily_report` / `error`。

暂停的最近结果另存 `LEIGOD_PAUSE_STATE`，供 `/l s` 快速读取。

**为什么不写本地文件跨容器共享**：AstrBot 与青龙由 NAS 应用中心托管（`docker-compose.yml` 里只有 `luker`），加挂载要重建容器，违反最小改动约束。环境变量是两者唯一共同可写的位置。

## 6. 测试记录

| 测试 | 方式 | 结果 |
|---|---|---|
| 指令解析 16 例（含大小写、前后空格、`/login` 不误判、Token 原样保留） | `python3 leigod_cmd.py --selftest` | 全部通过 |
| 青龙 OpenAPI 鉴权与环境变量读取 | 容器内读 `Apps` 表后调 `/open/auth/token` + `/open/envs` | 通过（11 个变量） |
| 未配置 Token 时暂停任务退出码 | `task leigod/leigod_pause.py --no-push` | 输出「未配置雷神 Token」，退出码 2 |
| 状态查询 | `task leigod/leigod_status.py` | 正确显示 Token 未配置、白名单 1 人、青龙凭据已配置 |
| 指令分发 7 例（帮助/状态/未知/缺参/多参/非白名单/群聊） | AstrBot 容器内跑 `handle()` | 全部通过 |
| 插件注册 | 重启 AstrBot 后查日志 | `Plugin astrbot_plugin_leigod_manager (1.0.0) by Jipai` + 「指令入口已就绪」 |
| 两个 cron 任务落库 | `GET /open/crons` | id 14 / 15 存在，原有 5 个未变 |
| **雷神真实接口（日志查询、暂停）** | 需要有效 Token | **未测**（等你提供 Token） |
| **QQ 真实收发** | 需要你发一条 `/l h` | **未测** |

## 7. 回滚

```bash
# 1) 停用/删除两个新任务（保留原有 5 个）
#    青龙后台 → 定时任务 → 删除「雷神定时暂停」「雷神每日日报」
#    或用 API：DELETE /open/crons  body [14,15]

# 2) 卸载插件
sudo rm -rf /vol1/1000/Docker/astrbot/data/plugins/astrbot_plugin_leigod_manager
sudo docker restart astrbot

# 3) 删除青龙侧脚本与状态
sudo rm -rf /vol1/1000/Docker/qinglong/scripts/leigod

# 4) 删除新增环境变量（LEIGOD_*），注意 LEIGOD_TOKEN 里存着 Token
#    青龙后台 → 环境变量 → 删除
```

回滚不影响原有 5 个任务与 `QQ_APP_ID` 等既有变量。

## 8. 排错

| 现象 | 检查 |
|---|---|
| QQ 发指令没反应 | `docker logs --since 10m astrbot \| grep leigod`；确认插件已加载、消息是私聊、发送者在白名单 |
| 回「无权限」 | `LEIGOD_ALLOWED_IDS` 是否是你的 openid（注意不是 QQ 号） |
| 回「青龙接口请求失败」 | 插件 config.json 的 `ql_base` 是否用局域网 IP；青龙应用是否还有 `envs` scope |
| `/l logs` 报 400006 | Token 过期，用 Via 重新提取后 `/l u` |
| 日报没有数字 | 当天确实没有操作；系统不会把「没记录」算成成功 |
| 暂停一直「未知」 | 调 `/open/...` 后复查 `pause_status_id` 仍不是 1，看 `LEIGOD_PAUSE_STATE` 里的 detail |

## 9. 安全

- `config.json` 与 `LEIGOD_QL_CLIENT_SECRET` 是敏感项，权限 600，**不要提交到 git**（`.gitignore` 已排除）。
- Token 只存青龙环境变量 `LEIGOD_TOKEN`，不进日志、不进事件记录、不在回复里回显。
- 指令入口只做白名单校验，不提供任意 shell 执行。

## 10. 入站链路踩坑记录（首次上线时全部踩到）

指令「没反应」时，按这个顺序排查，前三条与插件代码无关：

### 10.1 AstrBot 三个平台适配器默认全是禁用

```json
// /AstrBot/data/cmd_config.json
"platform": [
  {"id": "Kana", "type": "aiocqhttp", "enable": false},
  {"id": "Aki",  "type": "aiocqhttp", "enable": false},
  {"id": "Hex",  "type": "qq_official", "enable": false}   // ← 要用的这个
]
```

`enable: false` 时 AstrBot 根本没和 QQ 建立连接，消息不会到达任何插件。
处理：启用 `Hex`（官方 Bot，appid 与青龙 `QQ_APP_ID` 一致），重启 AstrBot。
**不要**为此重启 NapCat —— 那两个 aiocqhttp 容器已停两个月，本项目不需要它们。

### 10.2 启用后报 `100016 invalid appid or secret`

说明 `Hex.secret` 是旧的。用青龙里正在生效的 `QQ_APP_SECRET` 覆盖即可
（`tools/patch_qq_secret.py`）。注意两者长度可能相同，所以别靠长度判断。

### 10.3 AstrBot 自身白名单为空会拦截全部消息

`platform_settings.enable_id_white_list: true` + `id_whitelist: []` → 谁都不放行。
把接收者的 openid 加进 `id_whitelist`（`tools/enable_qq_official.py` 已包含）。
这和插件自己的 `LEIGOD_ALLOWED_IDS` 是两层独立校验，都要过。

### 10.4 验证连接

```bash
docker logs --since 5m astrbot | grep -a "QQOfficial"
# 正常：[QQOfficial] Websocket session starting. 且之后没有 100016
```

### 10.5 插件行为确认

```bash
docker logs --since 5m astrbot | grep -a leigod
# 正常：Plugin astrbot_plugin_leigod_manager (1.0.0) by Jipai
#       [leigod] 指令入口已就绪（/leigod 或 /l）
```

命令匹配用的是 `@filter.regex(r"^\s*/(?:leigod|l)(?:\s|$)")`，AstrBot 的实现是
`regex.search(message.strip())` 且**不受 wake_prefix 约束**，所以裸 `/l h` 即可触发。

