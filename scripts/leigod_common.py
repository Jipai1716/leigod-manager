#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""雷神加速器 Token 管理与定时暂停系统 —— 公共库（仅标准库依赖）。

被三处复用：
  1. 青龙定时任务（leigod_pause.py）
  2. Web 面板（panel/app.py）
  3. 命令行手工调试

一个实现，多处调用 —— 暂停逻辑只写一遍。

证据来源（见 docs/api-notes.md）：
  - 雷神官网前端 bundle /js/chunk-common.js / user.js
    · URL_USER_INFO   = /api/user/info
    · URL_USER_PAUSE  = /api/user/pause
    · URL_USER_RECOVER= /api/user/recover
    · URL_USER_PAUSELOG = /api/user/pause/lists
    · sign() 算法与硬编码 key
  - QQ 机器人 OpenAPI 推送范式
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

# --------------------------------------------------------------------------
# 常量
# --------------------------------------------------------------------------

LEIGOD_BASE = os.environ.get("LEIGOD_BASE_URL", "https://webapi.leigod.com")
LEIGOD_SIGN_KEY = "5C5A639C20665313622F51E93E3F2783"  # 取自官网 bundle，硬编码
LEIGOD_SUCCESS = 0
LEIGOD_TOKEN_EXPIRE = 400006

QQ_TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
QQ_API_BASE = "https://api.sgroup.qq.com"

DEFAULT_STATE_DIR = os.environ.get("LEIGOD_STATE_DIR", "/ql/data/scripts/leigod/state")
HISTORY_LIMIT = int(os.environ.get("LEIGOD_HISTORY_LIMIT", "2000"))


# --------------------------------------------------------------------------
# 配置
# --------------------------------------------------------------------------


def _env(*names, default=""):
    for name in names:
        if name:
            value = os.environ.get(name)
            if value not in (None, ""):
                return value
    return default


class Config:
    """所有配置都从环境变量读，方便青龙里统一管理。"""

    def __init__(self):
        # 青龙
        self.ql_base = _env("LEIGOD_QL_BASE_URL", "QL_BASE_URL", default="http://127.0.0.1:5700")
        self.ql_client_id = _env("LEIGOD_QL_CLIENT_ID", "QL_CLIENT_ID")
        self.ql_client_secret = _env("LEIGOD_QL_CLIENT_SECRET", "QL_CLIENT_SECRET")

        # 雷神 token 所在的青龙环境变量名
        self.token_env = _env("LEIGOD_TOKEN_ENV", default="LEIGOD_TOKEN")
        # 命令事件日志（跨容器共享，见 docs/development.md）
        self.cmdlog_env = _env("LEIGOD_CMDLOG_ENV", default="LEIGOD_CMDLOG")
        self.pause_state_env = _env("LEIGOD_PAUSE_STATE_ENV", default="LEIGOD_PAUSE_STATE")

        # QQ 机器人
        self.qq_app_id = _env("LEIGOD_QQ_APP_ID", "QQ_APP_ID")
        self.qq_app_secret = _env("LEIGOD_QQ_APP_SECRET", "QQ_APP_SECRET")
        self.qq_target = _env("LEIGOD_QQ_TARGET", "QQ_OPENID")
        self.allowed_ids = {
            x.strip() for x in _env("LEIGOD_ALLOWED_IDS", "QQ_ALLOWED_USER_IDS").split(",") if x.strip()
        }

        # 时间
        self.tz_name = _env("LEIGOD_TZ", "TIMEZONE", default="Asia/Shanghai")
        self.tz = _resolve_tz(self.tz_name)

        # 其他
        self.state_dir = _env("LEIGOD_STATE_DIR", default=DEFAULT_STATE_DIR)
        self.daily_time = _env("LEIGOD_DAILY_TIME", default="23:59")
        self.http_timeout = int(_env("LEIGOD_HTTP_TIMEOUT", default="20"))

    def describe(self) -> dict:
        """给 status 用的脱敏配置快照。"""
        return {
            "青龙地址": self.ql_base,
            "Token 变量名": self.token_env,
            "时区": self.tz_name,
            "日报时间": self.daily_time,
            "白名单人数": len(self.allowed_ids),
            "QQ 目标已配置": bool(self.qq_target),
            "青龙 API 凭据": bool(self.ql_client_id and self.ql_client_secret),
        }


def _resolve_tz(name: str):
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 - 没装 tzdata 时退回固定 +8
        return timezone(timedelta(hours=8))


def now(cfg: Config) -> datetime:
    return datetime.now(cfg.tz)


def fmt_ts(cfg: Config, ts: float | None = None) -> str:
    return datetime.fromtimestamp(ts or time.time(), cfg.tz).strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------


def http_post_json(url, body, headers=None, timeout=20):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get_json(url, params=None, headers=None, timeout=20):
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method="GET")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class LeigodError(Exception):
    """雷神接口返回非 0 code，或网络失败。"""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------
# 雷神客户端
# --------------------------------------------------------------------------


def sign_params(params: dict) -> dict:
    """按官网 bundle 的算法签名（md5，值为原始串不 urlencode）。"""
    ts = str(int(time.time()))
    merged = dict(params)
    merged["ts"] = ts
    ordered = {k: merged[k] for k in sorted(merged)}
    ordered["key"] = LEIGOD_SIGN_KEY
    raw = "&".join(f"{k}={ordered[k]}" for k in ordered)
    return {**params, "ts": ts, "sign": hashlib.md5(raw.encode("utf-8")).hexdigest()}


class LeigodClient:
    def __init__(self, token: str, timeout: int = 20):
        self.token = token
        self.timeout = timeout

    def _post(self, path: str, body: dict | None = None, signed: bool = False) -> dict:
        payload = {"account_token": self.token, "lang": "zh_CN", "os_type": 4}
        payload.update(body or {})
        if signed:
            payload = sign_params(payload)
        url = LEIGOD_BASE + path
        try:
            data = http_post_json(url, payload, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "ignore")[:200]
            raise LeigodError(f"HTTP {exc.code}: {detail}", code=exc.code) from exc
        except Exception as exc:  # noqa: BLE001
            raise LeigodError(f"网络请求失败: {exc}") from exc
        code = data.get("code")
        if code == LEIGOD_TOKEN_EXPIRE:
            raise LeigodError("Token 被官网拒绝（400006，通常表示已过期）", code=code)
        if code != LEIGOD_SUCCESS:
            raise LeigodError(str(data.get("msg") or f"code={code}"), code=code)
        return data

    # ---- 只读 ----
    def user_info(self) -> dict:
        return self._post("/api/user/info").get("data") or {}

    def pause_logs(self, size: int = 15) -> dict:
        data = self._post("/api/user/pause/lists", {"size": size})
        return data

    def is_paused(self) -> bool:
        info = self.user_info()
        return str(info.get("pause_status_id")) == "1"

    # ---- 写 ----
    def pause(self) -> str:
        return str(self._post("/api/user/pause").get("msg") or "")

    def recover(self) -> str:
        return str(self._post("/api/user/recover").get("msg") or "")


def parse_pause_logs(payload: dict, limit: int = 3) -> tuple[list[dict], str]:
    """把 /api/user/pause/lists 的响应整理成按时间倒序的记录列表。

    返回 (records, 说明)。字段名以实际响应为准，这里只做容错提取：
    官网返回结构可能把列表放在 data 下，也可能是 data.list / data.rows。
    """
    data = payload.get("data")
    rows: list[dict] = []
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        for key in ("list", "lists", "rows", "records", "items", "pause_list"):
            if isinstance(data.get(key), list):
                rows = data[key]
                break
    if not rows and isinstance(data, dict):
        # 单条记录的情形
        if any(k in data for k in ("pause_time", "start_time", "create_time")):
            rows = [data]
    if not rows:
        return [], "官网未返回时长记录"

    def sort_key(item):
        for key in ("create_time", "pause_time", "start_time", "time", "end_time", "ts"):
            value = item.get(key)
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                if value.isdigit():
                    return float(value)
                try:
                    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
                except Exception:  # noqa: BLE001
                    continue
        return 0.0

    rows = sorted(rows, key=sort_key, reverse=True)
    return rows[:limit], ""


def format_pause_logs(cfg: Config, rows: list[dict], note: str = "") -> str:
    if not rows:
        return "雷神官网时长日志\n\n" + (note or "官网未返回时长记录")
    lines = [f"雷神官网时长日志（最近 {len(rows)} 条）"]
    for idx, row in enumerate(rows, 1):
        lines.append(f"\n{idx}. " + _humanize_record(cfg, row))
    return "\n".join(lines)


def _humanize_record(cfg: Config, row: dict) -> str:
    """按 /api/user/pause/lists 的真实字段展示（实测字段：id/status/pause_time/resume_time/op_source）。"""
    parts = []

    pause_time = row.get("pause_time")
    if pause_time:
        parts.append(f"暂停时间：{_fmt_timeish(cfg, pause_time)}")

    if "resume_time" in row:
        resume_time = row.get("resume_time")
        parts.append(f"恢复时间：{_fmt_timeish(cfg, resume_time)}" if resume_time else "恢复时间：未恢复")

    if "status" in row:
        parts.append(f"状态码：{row.get('status')}")

    # 若官网以后加了其它字段，只展示含义明确的这几个
    for key, label in (
        ("pause_duration", "暂停时长"),
        ("duration", "时长"),
        ("surplus_time", "剩余时长"),
        ("use_time", "消耗时长"),
        ("msg", "说明"),
        ("remark", "备注"),
    ):
        value = row.get(key)
        if value in (None, "", 0, "0"):
            continue
        if key in ("pause_duration", "duration", "surplus_time", "use_time") and isinstance(
            value, (int, float)
        ):
            parts.append(f"{label}：{_fmt_duration(value)}")
        else:
            parts.append(f"{label}：{value}")

    if not parts:
        # 完全未知的结构：原样展示短 JSON，方便排查，但不编造
        text = json.dumps(row, ensure_ascii=False)
        parts.append(text[:180])
    return "，".join(parts)


def _fmt_timeish(cfg: Config, value) -> str:
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        number = float(value)
        if number > 1e12:  # 毫秒
            number /= 1000.0
        try:
            return datetime.fromtimestamp(number, cfg.tz).strftime("%Y-%m-%d %H:%M")
        except Exception:  # noqa: BLE001
            return str(value)
    return str(value)


def _fmt_duration(seconds) -> str:
    try:
        total = int(float(seconds))
    except Exception:  # noqa: BLE001
        return str(seconds)
    hours, rest = divmod(total, 3600)
    minutes = rest // 60
    if hours:
        return f"{hours}小时{minutes}分"
    return f"{minutes}分"


# --------------------------------------------------------------------------
# 青龙客户端
# --------------------------------------------------------------------------


class QinglongError(Exception):
    pass


class QinglongClient:
    """青龙 OpenAPI：环境变量读写。"""

    def __init__(self, base_url: str, client_id: str, client_secret: str, timeout: int = 20):
        self.base = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout
        self._token = None
        self._token_exp = 0.0

    def _auth(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        if not (self.client_id and self.client_secret):
            raise QinglongError("缺少青龙 API 凭据（LEIGOD_QL_CLIENT_ID / LEIGOD_QL_CLIENT_SECRET）")
        # 青龙 2.21.0-16 实测：GET /open/auth/token?client_id=&client_secret=
        # 注意不是 POST /open/auth/token，也不是 {appKey, appSecret} body。
        try:
            data = http_get_json(
                f"{self.base}/open/auth/token",
                {"client_id": self.client_id, "client_secret": self.client_secret},
                timeout=self.timeout,
            )
        except urllib.error.HTTPError as exc:
            raise QinglongError(f"青龙鉴权失败 HTTP {exc.code}") from exc
        except Exception as exc:  # noqa: BLE001
            raise QinglongError(f"青龙不可达: {exc}") from exc
        if data.get("code") != 200:
            raise QinglongError(f"青龙鉴权失败: {data.get('message')}")
        payload = data.get("data") or {}
        self._token = payload.get("token") or payload.get("access_token")
        self._token_exp = time.time() + float(payload.get("expiration") or 3600)
        if not self._token:
            raise QinglongError(f"青龙鉴权未返回 token: {str(data)[:200]}")
        return self._token

    def _call(self, method: str, path: str, body=None):
        token = self._auth()
        url = self.base + path
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "ignore")[:200]
            raise QinglongError(f"青龙接口 HTTP {exc.code}: {detail}") from exc
        except Exception as exc:  # noqa: BLE001
            raise QinglongError(f"青龙请求失败: {exc}") from exc

    def list_envs(self, search: str = "") -> list[dict]:
        data = self._call("GET", "/open/envs" + (f"?searchValue={urllib.parse.quote(search)}" if search else ""))
        if data.get("code") != 200:
            raise QinglongError(f"读取环境变量失败: {data.get('message')}")
        return data.get("data") or []

    def find_env(self, name: str) -> dict | None:
        for env in self.list_envs():
            if env.get("name") == name:
                return env
        return None

    def get_env_value(self, name: str) -> str | None:
        env = self.find_env(name)
        return None if env is None else (env.get("value") or "")

    def create_env(self, name: str, value: str, remarks: str = "") -> dict:
        data = self._call(
            "POST",
            "/open/envs",
            [{"name": name, "value": value, "remarks": remarks}],
        )
        if data.get("code") != 200:
            raise QinglongError(f"创建环境变量失败: {data.get('message')}")
        return data.get("data") or {}

    def update_env(self, env_id, name: str, value: str, remarks: str = "") -> dict:
        data = self._call(
            "PUT",
            "/open/envs",
            {"id": env_id, "name": name, "value": value, "remarks": remarks},
        )
        if data.get("code") != 200:
            raise QinglongError(f"更新环境变量失败: {data.get('message')}")
        return data.get("data") or {}

    def upsert_env(self, name: str, value: str, remarks: str = "") -> str:
        """写入成功返回 'created' / 'updated'；失败抛异常。"""
        env = self.find_env(name)
        if env is None:
            self.create_env(name, value, remarks)
            return "created"
        self.update_env(env.get("id"), name, value, remarks or (env.get("remarks") or ""))
        return "updated"

    # ---- 定时任务 ----
    CRON_KEYS = (
        "name",
        "command",
        "schedule",
        "task_before",
        "task_after",
        "log_name",
        "allow_multiple_instances",
        "work_dir",
        "extra_schedules",
        "sub_id",
    )

    def list_crons(self) -> list[dict]:
        data = self._call("GET", "/open/crons")
        payload = data.get("data") or {}
        return payload.get("data") or []

    def find_cron(self, name: str) -> dict | None:
        for cron in self.list_crons():
            if cron.get("name") == name:
                return cron
        return None

    def update_cron_schedule(self, cron_id: int, schedule: str) -> dict:
        """改某个任务的 cron。先按完整字段提交，被校验拒绝则退回最小字段。"""
        target = next((c for c in self.list_crons() if c.get("id") == cron_id), None)
        if target is None:
            raise QinglongError(f"任务 {cron_id} 不存在")

        full = {k: target.get(k) for k in self.CRON_KEYS if k in target}
        full.update({"id": cron_id, "schedule": schedule})
        try:
            response = self._call("PUT", "/open/crons", full)
            if response.get("code") == 200:
                return response.get("data") or {}
        except QinglongError:
            pass

        minimal = {
            "id": cron_id,
            "name": target.get("name"),
            "command": target.get("command"),
            "schedule": schedule,
        }
        response = self._call("PUT", "/open/crons", minimal)
        if response.get("code") != 200:
            raise QinglongError(f"更新定时规则失败: {response.get('message')}")
        return response.get("data") or {}


# --------------------------------------------------------------------------
# QQ 机器人推送
# --------------------------------------------------------------------------


class QQError(Exception):
    pass


def qq_access_token(cfg: Config) -> str:
    if not (cfg.qq_app_id and cfg.qq_app_secret):
        raise QQError("缺少 QQ_APP_ID / QQ_APP_SECRET")
    data = http_post_json(
        QQ_TOKEN_URL,
        {"appId": cfg.qq_app_id, "clientSecret": cfg.qq_app_secret},
        timeout=cfg.http_timeout,
    )
    token = data.get("access_token")
    if not token:
        raise QQError(f"获取 access_token 失败: {str(data)[:200]}")
    return token


def qq_send(cfg: Config, text: str, markdown: bool = True) -> str:
    """主动消息推送。markdown 失败自动降级纯文本。"""
    if not cfg.qq_target:
        raise QQError("缺少 QQ 目标 openid（QQ_OPENID / LEIGOD_QQ_TARGET）")
    token = qq_access_token(cfg)
    url = f"{QQ_API_BASE}/v2/users/{urllib.parse.quote(cfg.qq_target)}/messages"
    headers = {"Authorization": f"QQBot {token}"}

    if markdown:
        try:
            http_post_json(
                url,
                {
                    "msg_type": 2,
                    "markdown": {"content": text},
                    "msg_seq": int(time.time() * 1000) % 1000000,
                },
                headers,
                timeout=cfg.http_timeout,
            )
            return "markdown"
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "ignore")[:200]
            print(f"markdown 推送失败({exc.code}): {detail} —— 降级纯文本")
        except Exception as exc:  # noqa: BLE001
            print(f"markdown 推送异常: {exc} —— 降级纯文本")
    try:
        http_post_json(url, {"content": text, "msg_type": 0}, headers, timeout=cfg.http_timeout)
        return "text"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")[:200]
        raise QQError(f"推送失败 HTTP {exc.code}: {detail}") from exc
    except Exception as exc:  # noqa: BLE001
        raise QQError(f"推送失败: {exc}") from exc


# --------------------------------------------------------------------------
# 事件记录（跨容器共享：青龙环境变量 + 本地文件镜像）
# --------------------------------------------------------------------------


OPS = {
    "token_update": "Token 更新",
    "pause_trigger": "手动暂停触发",
    "pause_result": "暂停任务结果",
    "logs_query": "官网日志查询",
    "daily_report": "每日汇总",
    "error": "错误",
}


class Store:
    """事件日志。

    面板容器与青龙容器没有共享挂载，唯一共同可写的位置是青龙环境变量。
    因此事件记录以 LEIGOD_CMDLOG（JSON 数组，最多 100 条）为准，本地
    state/history.jsonl 只作离线镜像与排查用，不会被日报重复统计。
    """

    MAX_EVENTS = 100

    def __init__(self, cfg: Config, ql: QinglongClient | None = None):
        self.cfg = cfg
        self.ql = ql

    # ---- 事件 ----
    def add_event(self, op: str, result: str, detail: str = "") -> dict:
        event = {
            "ts": int(time.time()),
            "time": fmt_ts(self.cfg),
            "op": op,
            "op_label": OPS.get(op, op),
            "result": result,
            "detail": (detail or "")[:300],
        }
        events = self.read_events()
        events.append(event)
        events = events[-self.MAX_EVENTS :]
        if self.ql is not None:
            try:
                self.ql.upsert_env(
                    self.cfg.cmdlog_env,
                    json.dumps(events, ensure_ascii=False),
                    "雷神管理器事件日志（勿手改）",
                )
            except QinglongError as exc:
                print(f"写入事件日志失败: {exc}")
        self._mirror(event)
        return event

    def read_events(self) -> list[dict]:
        if self.ql is None:
            return []
        try:
            raw = self.ql.get_env_value(self.cfg.cmdlog_env)
        except QinglongError:
            return []
        if not raw:
            return []
        try:
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except Exception:  # noqa: BLE001
            return []

    def _mirror(self, event: dict):
        try:
            os.makedirs(os.path.dirname(self._mirror_path()), exist_ok=True)
            with open(self._mirror_path(), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
            self._trim_mirror()
        except Exception as exc:  # noqa: BLE001 - 镜像失败不影响主流程
            print(f"本地镜像写入失败: {exc}")

    def _mirror_path(self) -> str:
        return os.path.join(self.cfg.state_dir, "history.jsonl")

    def _trim_mirror(self):
        path = self._mirror_path()
        try:
            with open(path, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
            if len(lines) > HISTORY_LIMIT:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.writelines(lines[-HISTORY_LIMIT:])
        except Exception:  # noqa: BLE001
            pass

    # ---- 暂停状态 ----
    def set_pause_state(self, state: dict):
        if self.ql is None:
            return
        try:
            self.ql.upsert_env(
                self.cfg.pause_state_env,
                json.dumps(state, ensure_ascii=False),
                "雷神暂停任务最近结果（勿手改）",
            )
        except QinglongError as exc:
            print(f"写入暂停状态失败: {exc}")

    def get_pause_state(self) -> dict:
        if self.ql is None:
            return {}
        try:
            raw = self.ql.get_env_value(self.cfg.pause_state_env)
            return json.loads(raw) if raw else {}
        except Exception:  # noqa: BLE001
            return {}


# --------------------------------------------------------------------------
# 业务动作
# --------------------------------------------------------------------------


def get_token(cfg: Config, ql: QinglongClient) -> str | None:
    value = ql.get_env_value(cfg.token_env)
    return value.strip() if value and value.strip() else None


def update_token(cfg: Config, ql: QinglongClient, store: Store, token: str) -> tuple[bool, str]:
    """把新 Token 写进青龙现有变量。不验证有效性。"""
    token = (token or "").strip()
    if not token:
        return False, "雷神 Token 更新失败\n原因：Token 为空"
    try:
        action = ql.upsert_env(cfg.token_env, token, "雷神加速器 account_token")
    except QinglongError as exc:
        store.add_event("token_update", "失败", str(exc))
        return False, (
            "雷神 Token 更新失败\n"
            f"原因：{exc}\n"
            "原有配置：未确认发生变更"
        )
    store.add_event("token_update", "成功", f"{cfg.token_env} {action}")
    return True, (
        "雷神 Token 更新完成\n"
        f"写入变量：{cfg.token_env}\n"
        f"写入结果：成功（{action}）\n"
        "有效性验证：未执行"
    )


def do_pause(cfg: Config, ql: QinglongClient, store: Store, trigger: str = "manual") -> tuple[bool, str]:
    """执行暂停：先查状态，未暂停才暂停，再复查。写事件 + 暂停状态。"""
    token = get_token(cfg, ql)
    if not token:
        store.add_event("error", "失败", "未配置 Token")
        return False, "暂停任务失败：未配置雷神 Token，请先发送 /l u <Token>"

    store.add_event("pause_trigger", "已触发", f"来源={trigger}")
    client = LeigodClient(token, timeout=cfg.http_timeout)
    started = time.time()
    try:
        paused_before = client.is_paused()
        if paused_before:
            msg = "当前已是暂停状态，未重复调用暂停接口"
            ok = True
        else:
            api_msg = client.pause()
            paused_after = client.is_paused()
            ok = paused_after
            msg = f"暂停接口返回：{api_msg or '无消息'}；复查 pause_status_id={'1' if paused_after else '0'}"
    except LeigodError as exc:
        store.add_event("pause_result", "失败", str(exc))
        store.set_pause_state(
            {"ts": int(time.time()), "time": fmt_ts(cfg), "result": "失败", "detail": str(exc)}
        )
        return False, f"暂停任务失败\n原因：{exc}"

    state = {
        "ts": int(time.time()),
        "time": fmt_ts(cfg),
        "result": "成功" if ok else "未知",
        "detail": msg,
        "elapsed": round(time.time() - started, 1),
        "trigger": trigger,
    }
    store.set_pause_state(state)
    store.add_event("pause_result", state["result"], msg)
    header = "暂停成功" if ok else "暂停结果未知"
    return ok, f"{header}\n{msg}\n耗时：{state['elapsed']}s"


def fetch_logs(cfg: Config, ql: QinglongClient, store: Store, limit: int = 3) -> tuple[bool, str]:
    token = get_token(cfg, ql)
    if not token:
        store.add_event("logs_query", "失败", "未配置 Token")
        return False, "官网日志查询失败：未配置雷神 Token，请先发送 /l u <Token>"
    client = LeigodClient(token, timeout=cfg.http_timeout)
    try:
        payload = client.pause_logs(size=15)
    except LeigodError as exc:
        store.add_event("logs_query", "失败", str(exc))
        return False, f"官网日志查询失败\n原因：{exc}"
    rows, note = parse_pause_logs(payload, limit=limit)
    store.add_event("logs_query", "成功" if rows else "无记录", f"{len(rows)} 条")
    return True, format_pause_logs(cfg, rows, note)


def query_pause_state(cfg: Config, ql: QinglongClient) -> dict:
    """查询当前是否处于暂停状态（直接问官网，不做本地推断）。"""
    token = get_token(cfg, ql)
    if not token:
        return {"state": "unknown", "reason": "未配置 Token", "checked_at": fmt_ts(cfg)}
    try:
        info = LeigodClient(token, timeout=cfg.http_timeout).user_info()
    except LeigodError as exc:
        return {"state": "unknown", "reason": str(exc), "checked_at": fmt_ts(cfg)}

    pid = str(info.get("pause_status_id", ""))
    if pid == "1":
        state = "paused"
    elif pid == "0":
        state = "running"
    else:
        state = "unknown"

    extra = {}
    for key in ("surplus_time", "surplus_time_str", "expire_time", "nickname", "mobile"):
        if info.get(key) not in (None, "", 0, "0"):
            extra[key] = info[key]

    return {
        "state": state,
        "pause_status_id": pid,
        "checked_at": fmt_ts(cfg),
        "extra": extra,
        "raw_keys": sorted(info.keys()),
    }


_CRON_PRESETS = [
    ("每 6 小时", "0 */6 * * *"),
    ("每天 03:00", "0 3 * * *"),
    ("工作日 03:00", "0 3 * * 1-5"),
    ("休息日 03:00", "0 3 * * 6,0"),
    ("工作日 00:00 与 12:00", "0 0,12 * * 1-5"),
    ("每 2 小时（含夜间）", "0 */2 * * *"),
]


def cron_presets() -> list[dict]:
    return [{"label": label, "cron": cron} for label, cron in _CRON_PRESETS]


def parse_cron(expr: str) -> dict:
    """极简 cron 解析：校验 5 段与数值范围 + 生成中文描述。不追求覆盖全部语法。"""
    expr = (expr or "").strip()
    parts = expr.split()
    if len(parts) != 5:
        return {"ok": False, "error": "需要 5 段：分 时 日 月 周"}
    if "?" in expr:
        return {"ok": False, "error": "不支持 ? ，请用 *"}
    for index, part in enumerate(parts):
        if not all(ch.isdigit() or ch in "*/,-" for ch in part):
            return {"ok": False, "error": f"第 {index + 1} 段含非法字符"}

    limits = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]
    names = ["分", "时", "日", "月", "周"]
    for index, part in enumerate(parts):
        low, high = limits[index]
        for token in part.replace("*", "").split(","):
            for piece in token.split("-"):
                piece = piece.split("/")[0]
                if piece.isdigit() and not (low <= int(piece) <= high):
                    return {
                        "ok": False,
                        "error": f"{names[index]}字段超出范围 {low}-{high}：{piece}",
                    }
    return {"ok": True, "desc": _describe_cron(parts)}


def _describe_cron(parts: list[str]) -> str:
    minute, hour, dom, month, dow = parts
    pieces = []

    if minute.startswith("*/"):
        pieces.append(f"每 {minute[2:]} 分钟")
    elif minute == "0":
        pieces.append("整点")
    elif minute == "*":
        pieces.append("每分钟")
    else:
        pieces.append(f"第 {minute} 分")

    if hour == "*":
        pieces.append("每小时")
    elif hour.startswith("*/"):
        pieces.append(f"每 {hour[2:]} 小时")
    else:
        hours = [h.strip() for h in hour.split(",") if h.strip()]
        if all(h.isdigit() for h in hours):
            pieces.append("在 " + "、".join(f"{int(h):02d}:00" for h in hours))
        else:
            pieces.append(f"时={hour}")

    if month != "*":
        pieces.append(f"月={month}")

    if dom != "*":
        pieces.append(f"每月 {dom} 日")

    if dow != "*":
        names = {"0": "周日", "1": "周一", "2": "周二", "3": "周三", "4": "周四",
                 "5": "周五", "6": "周六", "7": "周日"}
        if dow in ("1-5", "1,2,3,4,5"):
            pieces.append("仅工作日")
        elif dow in ("6,0", "0,6", "6,7", "7,6", "5,6", "sat,sun"):
            pieces.append("仅休息日")
        else:
            tokens = []
            for token in dow.split(","):
                if "-" in token:
                    start, _, end = token.partition("-")
                    if start.isdigit() and end.isdigit():
                        tokens.append(f"{names.get(start, start)}~{names.get(end, end)}")
                    else:
                        tokens.append(token)
                else:
                    tokens.append(names.get(token.strip(), token))
            pieces.append("周=" + "、".join(tokens))
    else:
        pieces.append("每天")

    return "，".join(pieces)


def build_status(cfg: Config, ql: QinglongClient, store: Store) -> str:
    lines = ["雷神管理器状态"]

    try:
        token = get_token(cfg, ql)
    except QinglongError as exc:
        return f"雷神管理器状态\n\n青龙接口不可用：{exc}"
    lines.append(f"\nToken：{'已配置' if token else '未配置'}")
    if token:
        lines.append(f"Token 变量：{cfg.token_env}（长度 {len(token)}）")

    events = store.read_events()
    token_events = [e for e in events if e.get("op") == "token_update"]
    if token_events:
        last = token_events[-1]
        lines.append(f"最近更新：{last.get('time')} · {last.get('result')}")
    else:
        lines.append("最近更新：无记录")

    pause_state = store.get_pause_state()
    if pause_state:
        lines.append(
            f"最近暂停：{pause_state.get('time')} · {pause_state.get('result')}"
            f"（{pause_state.get('trigger', 'unknown')}）"
        )
    else:
        lines.append("最近暂停：无记录")

    log_events = [e for e in events if e.get("op") == "logs_query"]
    if log_events:
        last = log_events[-1]
        lines.append(f"最近日志查询：{last.get('time')} · {last.get('result')}")
    else:
        lines.append("最近日志查询：无记录")

    errors = [e for e in events if e.get("result") == "失败"]
    lines.append(f"最近错误：{errors[-1].get('detail') if errors else '无'}")

    info = cfg.describe()
    lines.append("\n配置：" + "，".join(f"{k}={v}" for k, v in info.items()))
    return "\n".join(lines)


def build_history(store: Store, limit: int = 10) -> str:
    events = store.read_events()
    if not events:
        return "本地执行记录：暂无记录"
    rows = events[-limit:][::-1]
    lines = [f"本地执行记录（最近 {len(rows)} 条）"]
    for event in rows:
        detail = event.get("detail") or ""
        detail = f" · {detail}" if detail else ""
        lines.append(
            f"{event.get('time', '?')} · {event.get('op_label', event.get('op'))}"
            f" · {event.get('result')}{detail}"
        )
    return "\n".join(lines)


def build_daily_report(cfg: Config, store: Store, day: str | None = None) -> str:
    """按天汇总事件。没有记录的项目明确写“无”，不把缺失当成功。"""
    today = day or now(cfg).strftime("%Y-%m-%d")
    events = [e for e in store.read_events() if str(e.get("time", "")).startswith(today)]

    def pick(op):
        return [e for e in events if e.get("op") == op]

    token_updates = pick("token_update")
    pause_results = pick("pause_result")
    pause_triggers = pick("pause_trigger")
    log_queries = pick("logs_query")
    errors = [e for e in events if e.get("result") == "失败"]

    def count(rows, result):
        return sum(1 for e in rows if e.get("result") == result)

    ok_n = count(pause_results, "成功")
    fail_n = count(pause_results, "失败")
    unknown_n = len(pause_results) - ok_n - fail_n

    last_ok_pause = next((e for e in reversed(pause_results) if e.get("result") == "成功"), None)
    last_token = token_updates[-1] if token_updates else None
    last_log = log_queries[-1] if log_queries else None

    lines = [
        "【雷神自动化日报】",
        f"日期：{today}",
        "",
        "Token 更新：",
        f"- 今日更新：{len(token_updates)} 次",
        f"- 最近更新时间：{last_token.get('time') if last_token else '无'}",
        "",
        "暂停任务：",
        f"- 执行次数：{len(pause_results)}",
        f"- 成功：{ok_n}",
        f"- 失败：{fail_n}",
        f"- 未知：{unknown_n}",
        f"- 手工触发：{len(pause_triggers)} 次",
        f"- 最近成功暂停：{last_ok_pause.get('time') if last_ok_pause else '无'}",
        "",
        "官网日志查询：",
        f"- 查询次数：{len(log_queries)}",
        f"- 最近结果：{(last_log.get('result') + '（' + (last_log.get('detail') or '') + '）') if last_log else '无'}",
        "",
        "异常：",
    ]
    if errors:
        for event in errors[-3:]:
            lines.append(f"- {event.get('time')} {event.get('detail')}")
    else:
        lines.append("- 无")
    return "\n".join(lines)
