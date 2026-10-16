#!/usr/bin/env python3
"""Qoder CN 每日签到（云端版）。

使用 campaigns API（自动适应活动 ID 变化）：
  GET  /sash/api/v1/me/campaigns          — 拉取活动列表
  POST /sash/api/v1/me/campaigns/{id}/claim — 领取可签到活动

认证: Bearer token（dt- 前缀，约 30 天有效期）
注意: 必须带 Cosy-* 请求头，否则 campaigns API 返回空列表。
幂等: 409 AlreadyExists 视为已签到；无 CLAIMABLE 活动时正常退出。

用法:
  云端: 环境变量 QODER_TOKEN=<token> python3 qoder_checkin.py
  本地: QODER_TOKEN=$(python3 tools/decrypt_qoder_token.py --stdout) python3 qoder_checkin.py
"""
import json
import os
import socket
import ssl
import sys
import urllib.request
import urllib.error
from datetime import datetime

API_BASE = 'https://openapi.qoder.com.cn'
CAMPAIGNS_PATH = '/sash/api/v1/me/campaigns'

# GitHub Actions 有完整证书链；本地 macOS Homebrew Python 可能缺失根证书
_ssl_ctx = ssl.create_default_context()
try:
    import certifi
    _ssl_ctx.load_verify_locations(certifi.where())
except ImportError:
    pass


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def get_token():
    token = os.environ.get('QODER_TOKEN', '').strip()
    if not token:
        log('ERROR 缺少 QODER_TOKEN 环境变量')
        sys.exit(1)
    return token


def get_headers(token):
    return {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'User-Agent': 'Qoder',
        'Cosy-ClientType': '10',
        'Cosy-Version': '0.3.3',
        'Cosy-MachineOS': 'darwin',
        'Cosy-MachineHostname': socket.gethostname(),
    }


def api_call(token, method, path, body=None):
    url = API_BASE + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method, headers=get_headers(token))
    try:
        with urllib.request.urlopen(req, timeout=30, context=_ssl_ctx) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {'message': str(e)}


def main():
    token = get_token()

    # 1. 拉取活动列表
    log('查询签到活动...')
    code, result = api_call(token, 'GET', CAMPAIGNS_PATH)
    if code != 200:
        log(f'ERROR 查询活动失败 HTTP {code}: {json.dumps(result, ensure_ascii=False)[:200]}')
        sys.exit(1)

    campaigns = result.get('campaigns', [])
    if not campaigns:
        log('SKIP 当前无签到活动（活动可能尚未开始或已结束）')
        return

    # 2. 筛选可领取的活动
    claimable = [c for c in campaigns if c.get('claimStatus') == 'CLAIMABLE' and c.get('actionType') == 'CLAIM_BENEFIT']
    if not claimable:
        claimed = [c for c in campaigns if c.get('claimStatus') == 'CLAIMED']
        if claimed:
            log(f"SKIP 今日已签到（{len(claimed)} 个活动已领取）")
        else:
            log(f"SKIP 无可领取活动，当前活动状态: {[(c.get('campaignKey'), c.get('claimStatus')) for c in campaigns]}")
        return

    # 3. 逐个领取
    success_count = 0
    for camp in claimable:
        camp_id = camp.get('campaignId')
        camp_key = camp.get('campaignKey', camp_id)
        benefit = camp.get('benefit', {})
        reward_amount = benefit.get('amount', '?')
        log(f'领取活动: {camp_key} (id={camp_id}) 奖励 {reward_amount} credits')

        code, claim_result = api_call(
            token, 'POST', f'{CAMPAIGNS_PATH}/{camp_id}/claim', body={}
        )

        if code == 200:
            status = claim_result.get('status', 'CLAIMED')
            log(f"SUCCESS 签到成功: {camp_key}, 奖励 {reward_amount} credits, 状态={status}")
            success_count += 1
        elif code == 409:
            log(f"SKIP 活动已领取: {camp_key}")
            success_count += 1
        else:
            log(f"ERROR 领取失败 HTTP {code}: {json.dumps(claim_result, ensure_ascii=False)[:200]}")

    if success_count == 0:
        log('ERROR 所有活动领取失败')
        sys.exit(1)

    # 4. 查询最终状态
    code, final = api_call(token, 'GET', CAMPAIGNS_PATH)
    if code == 200:
        log(f"活动状态: claimable={final.get('claimable')}")


if __name__ == '__main__':
    main()
