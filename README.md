# 雷神加速器 Token 管理与定时暂停

NAS 上的**Docker Web 面板**做控制台，**青龙**跑定时暂停并存 Token，**QQ 机器人只在失败时报警**。

没有 `/命令`、不接大模型、不验证 Token 有效性、不自动刷新 Token。

```
Via / 油猴脚本（提取 Token）
      │ 粘贴 或 一键推送
      ▼
雷神管理器面板（Docker，:5788，无密码）
      │ 写环境变量 / 改 cron
      ├───────────────► 青龙面板（存 LEIGOD_TOKEN + 任务「雷神定时暂停」）
      │                       │ 按 cron 执行
      │                       ▼
      │                 雷神 /api/user/pause
      │                       │ 仅失败/未知时
      │                       ▼
      └── 读状态/事件 ──── QQ 机器人报警
```

## 面板功能

| 功能 | 说明 |
|---|---|
| **当前暂停状态** | 直接问官网 `/api/user/info` 的 `pause_status_id`，显示「已暂停 / 未暂停 / 未知」，不做本地推断 |
| **定时规则编辑** | 直接改青龙任务「雷神定时暂停」的 cron；内置预设（每 6 小时、每天 3 点、工作日 3 点、休息日 3 点、工作日 0/12 点…），支持手写任意 5 段 cron |
| 更新 Token | 写入青龙 `LEIGOD_TOKEN`，回复明确写「有效性验证：未执行」 |
| 立即暂停 | 执行一次暂停；失败自动推 QQ |
| 官网时长日志 | 最近 3 条暂停记录（暂停时间 / 恢复时间 / 状态码） |
| 执行记录 | 最近的操作与结果 |

面板**无访问密码**，仅限局域网使用，请勿暴露到公网。

## 提取 Token 的三种方式

1. **油猴脚本**（桌面浏览器）`tampermonkey/leigod-token.user.js`
   - 登录雷神官网后右下角出现「提取 Token」「推送到面板」
   - 首次点「推送到面板」会让你填面板地址，之后记住
2. **Via 用户脚本**（手机）`via/leigod-token.user.js` —— 只做「复制」，粘贴到面板
3. 浏览器 F12 → Console：`JSON.parse(localStorage.getItem('account_token')).account_token`

## 部署

```bash
# 1) 上传
tar -czf leigod.tgz -C leigod-manager panel scripts
scp leigod.tgz jipai@<NAS>:/tmp/
ssh jipai@<NAS> 'rm -rf /tmp/leigod-deploy2 && mkdir -p /tmp/leigod-deploy2 && tar -xzf /tmp/leigod.tgz -C /tmp/leigod-deploy2'

# 2) 构建 + 启动
ssh jipai@<NAS> 'NAS_SUDO_PW=... bash /tmp/deploy_panel.sh'
```

基础镜像 `python:3.11-slim`，**纯标准库，无 pip 依赖**，容器无状态（数据全在青龙）。

也可以把 `panel/docker-compose.yml` 当作 NAS「Docker 应用」导入，环境变量见文件头注释。

## 定时任务

| id | 名称 | 命令 | 默认 cron |
|---|---|---|---|
| 14 | 雷神定时暂停 | `task leigod/leigod_pause.py` | `0 */6 * * *` |

cron 在面板里改，改完会回读校验。原有 5 个任务（天气/必应×2/qB×2）不动。

## 配置

`/vol1/1000/Docker/leigod-panel/panel.env`（600）：

```text
LEIGOD_QL_BASE_URL=http://<NAS_IP>:5700     # 必须用局域网 IP，容器里 127.0.0.1 不通
LEIGOD_QL_CLIENT_ID=<青龙 API 应用 ID>
LEIGOD_QL_CLIENT_SECRET=<青龙 API 应用密钥>
LEIGOD_TZ=Asia/Shanghai
LEIGOD_PAUSE_TASK_NAME=雷神定时暂停
```

QQ 报警复用青龙已有的 `QQ_APP_ID` / `QQ_APP_SECRET` / `QQ_OPENID`。

## 目录

```
panel/                    Web 面板（Dockerfile + app.py + compose）
scripts/                  青龙侧脚本
  leigod_common.py        公共库（雷神客户端 / 青龙客户端 / QQ 推送 / 事件 / cron 工具）
  leigod_pause.py         定时暂停（仅失败推送）
  leigod_{update_token,logs,status,history}.py   命令行工具
tampermonkey/             油猴脚本（桌面，可直推面板）
via/                      Via 用户脚本（手机，复制粘贴）
docs/env-survey.md        环境与接口调查记录（含证据）
docs/development.md       实现、部署、回滚、排错
tools/                    部署与诊断脚本
```

## 已知限制

- `account_token` 约 7 天过期，过期后重新提取并在面板更新；系统不会自动刷新。
- 面板无鉴权，别暴露公网。
- 无日报（按需求去掉），只有失败报警。
- cron 描述器只覆盖常见写法，复杂表达式以青龙实际调度为准（保存时会回读校验）。
