#!/usr/bin/env python3
"""WorkBuddy 每日签到（云端版）。token 从环境变量读取，不落盘。"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime

# 实测 copilot.tencent.com / codebuddy.cn / workbuddy.cn 三个域名背后是同一套 API，
# 默认保留 codebuddy.cn，需要时可用 WORKBUDDY_ENDPOINT 覆盖。
API_BASE = os.environ.get("WORKBUDDY_ENDPOINT", "https://www.codebuddy.cn").rstrip("/")
CHECKIN_URL = f"{API_BASE}/v2/billing/meter/daily-checkin"
# 用 checkin-activity-status 而不是 checkin-status：后者在 5.8.3 上返回的
# streak_days / week_checkin_days 恒为 0（本仓库原作者的注释也提到该接口不可靠），
# 前者才给出真实连登数据。
STATUS_URL = f"{API_BASE}/v2/billing/meter/checkin-activity-status"


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def post(url, headers):
    req = urllib.request.Request(url, data=b"{}", method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        log(f"HTTP {e.code}: {body[:300]}")
        try:
            return json.loads(body)
        except Exception:
            return None
    except Exception as e:
        log(f"请求失败: {e}")
        return None


def main():
    token = os.environ.get("WORKBUDDY_ACCESS_TOKEN", "").strip()
    uid = os.environ.get("WORKBUDDY_UID", "").strip()
    if not token:
        log("[x] 缺少 WORKBUDDY_ACCESS_TOKEN")
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "WorkBuddy-Checkin/1.0",
        "X-Domain": "www.codebuddy.cn",
    }
    if uid:
        headers["X-User-Id"] = uid

    # 直接签到。注意：checkin-status 的 today_checked_in 字段实测不可靠（UI 已签仍显示
    # false），以 daily-checkin 的返回码为准：0=成功，10001=今天已签。
    r = post(CHECKIN_URL, headers)
    if r is None:
        sys.exit(1)
    code = r.get("code")
    msg = r.get("msg", "")
    if code == 0:
        log(f"签到成功: {json.dumps(r.get('data') or {}, ensure_ascii=False)[:300]}")
    elif code == 10001:
        log(f"今天已签到: {msg}")
    else:
        log(f"[x] 签到失败 code={code} msg={msg}")
        sys.exit(1)

    # 签到后查一次状态展示积分（尽力而为，失败不影响结果）
    st = post(STATUS_URL, headers)
    if st and st.get("code") == 0:
        d = st.get("data") or {}
        log(f"账户状态: 连续{d.get('streak_days')}天 本周{d.get('week_checkin_days')}天")


if __name__ == "__main__":
    main()
