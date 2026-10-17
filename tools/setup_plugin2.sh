#!/bin/bash
PW="${NAS_SUDO_PW:?需要设置 NAS_SUDO_PW}"
S() { echo "$PW" | sudo -S -p '' "$@" 2>/dev/null; }
SO() { echo "$PW" | sudo -S -p '' "$@"; }

PLUGIN_DIR=/vol1/1000/Docker/astrbot/data/plugins/astrbot_plugin_leigod_manager

# 配置文件由青龙容器内生成，再拷回宿主机
SO docker cp qinglong:/tmp/plugin_config.json /tmp/plugin_config.json
echo "=== 拷贝结果 ==="
ls -l /tmp/plugin_config.json

echo "=== 写入插件目录 ==="
SO cp /tmp/plugin_config.json "$PLUGIN_DIR/config.json"
SO chmod 600 "$PLUGIN_DIR/config.json"
SO mkdir -p "$PLUGIN_DIR/state"
SO chmod 777 "$PLUGIN_DIR/state"
SO ls -l "$PLUGIN_DIR"

echo
echo "=== 容器内导入自检（带 config.json）==="
SO docker exec astrbot python3 -c "
import sys
sys.path.insert(0, '/AstrBot/data/plugins/astrbot_plugin_leigod_manager/lib')
import leigod_cmd, leigod_common, json, os
# 模拟插件加载时的 config.json -> env 转换
p='/AstrBot/data/plugins/astrbot_plugin_leigod_manager/config.json'
d=json.load(open(p))
for k,v in (('ql_base','LEIGOD_QL_BASE_URL'),('ql_client_id','LEIGOD_QL_CLIENT_ID'),('ql_client_secret','LEIGOD_QL_CLIENT_SECRET'),('token_env','LEIGOD_TOKEN_ENV'),('tz','LEIGOD_TZ')):
    os.environ.setdefault(v, d[k])
os.environ.setdefault('LEIGOD_ALLOWED_IDS', ','.join(d['allowed_ids']))
os.environ.setdefault('LEIGOD_STATE_DIR', d['state_dir'])
cfg=leigod_common.Config()
print('ql_base:', cfg.ql_base)
print('allowed:', len(cfg.allowed_ids), 'tz:', cfg.tz_name)
from leigod_common import QinglongClient
ql=QinglongClient(cfg.ql_base, cfg.ql_client_id, cfg.ql_client_secret)
print('env names:', [e['name'] for e in ql.list_envs()])
"
