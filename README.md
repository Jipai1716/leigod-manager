# 雷神加速器 Token 管理与定时暂停

在现有 NAS 上运行：**Docker Web 面板**做控制台，**青龙**跑定时暂停并存 Token，**QQ 机器人只在失败时报警**。

没有 `/命令`、不接大模型、不自动刷新 Token、不验证 Token 有效性。

```
Via 浏览器（提取 Token）
      │ 手抄到面板
      ▼
雷神管理器面板（Docker，:5788）
      │ 写环境变量
      ├───────────────► 青龙面板（存 LEIGOD_TOKEN）
      │                       │ 每 6 小时
      │                       ▼
      │                 雷神 /api/user/pause
      │                       │ 仅在失败/未知时
      │                       ▼
      └── 读状态/事件 ──── QQ 机器人报警
```

## 它做什么

| 能力 | 在哪 |
|---|---|
| 粘贴/更新 Token（不验证有效性） | 面板首页 |
| 查看 Token 是否已配置、最近更新 | 面板「概览」 |
| 手动暂停一次 | 面板「立即暂停」 |
| 查官网最近 3 条时长日志 | 面板「查官网时长日志」 |
| 查看本地执行记录 | 面板「最近执行记录」 |
| 定时暂停（每 6 小时） | 青龙任务 `雷神定时暂停` |
| 失败报警 | 暂停失败时推 QQ，成功不打扰 |

## 部署

面板是一个独立容器（`leigod-panel`），基础镜像 `python:3.11-slim`，**纯标准库，无 pip 依赖**。

```bash
# 1) 上传代码
tar -czf leigod.tgz -C leigod-manager panel scripts
scp leigod.tgz jipai@<NAS>:/tmp/ && ssh jipai@<NAS> 'mkdir -p /tmp/leigod-deploy2 && tar -xzf /tmp/leigod.tgz -C /tmp/leigod-deploy2'

# 2) 构建 + 启动（需要 sudo）
ssh jipai@<NAS> 'NAS_SUDO_PW=... bash /tmp/deploy_panel.sh'
```

`deploy_panel.sh` 会：生成 16 位访问密码 → 写 `/vol1/1000/Docker/leigod-panel/panel.env`（600）
→ 构建镜像 → 启动容器（`--restart unless-stopped`，端口 5788）。

访问 `http://<NAS>:5788`，用 `panel.env` 里的 `LEIGOD_PANEL_PASSWORD` 登录。

也可以把 `panel/docker-compose.yml` 作为 NAS「Docker 应用」导入（需要同目录 `.env`）。

## 配置

`/vol1/1000/Docker/leigod-panel/panel.env`：

```text
LEIGOD_PANEL_PASSWORD=访问密码
LEIGOD_QL_BASE_URL=http://192.168.10.110:5700     # 容器访问青龙的地址，必须用局域网 IP
LEIGOD_QL_CLIENT_ID=青龙 API 应用 ID
LEIGOD_QL_CLIENT_SECRET=青龙 API 应用密钥
LEIGOD_TZ=Asia/Shanghai
```

QQ 报警复用青龙里已有的 `QQ_APP_ID` / `QQ_APP_SECRET` / `QQ_OPENID`。

## 定时任务

| id | 名称 | 命令 | cron |
|---|---|---|---|
| 14 | 雷神定时暂停 | `task leigod/leigod_pause.py` | `0 */6 * * *` |

改频率只改这一个任务的 cron。原有 5 个任务（天气/必应×2/qB×2）完全没动。

## 目录

```
panel/                 Web 面板（Dockerfile + app.py + compose）
scripts/               青龙侧脚本
  leigod_common.py     公共库：雷神客户端 / 青龙客户端 / QQ 推送 / 事件存储
  leigod_pause.py      定时暂停（仅失败推送）
  leigod_{update_token,logs,status,history}.py  命令行工具
via/leigod-token.user.js   Via 用户脚本（提取 Token）
docs/env-survey.md     环境与接口调查记录（含证据）
docs/development.md    实现细节、部署、回滚、排错
tools/                 部署与诊断脚本
```

## 已知限制

- 雷神 `account_token` 约 **7 天**过期，过期后需重新提取并在面板更新；系统不会自动刷新。
- `/api/user/pause/lists` 字段以官网实际响应为准，解析器做了多结构容错。
- 面板是单用户密码登录，别直接暴露到公网。
- 无日报功能（按需求去掉），只有失败报警。

详细设计见 `docs/development.md`。
