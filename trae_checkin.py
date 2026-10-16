#!/usr/bin/env python3
"""TRAE SOLO 每日签到（云端版）。

凭证从本地 TRAE SOLO CN 客户端解密获取（byteCrypto 算法复刻），
或在 GitHub Actions 中使用 Secrets 注入 TRAE_JWT。

用法:
  本地: python3 trae_checkin.py --token-file /tmp/trae_auth_decrypted.json
  云端: 环境变量 TRAE_JWT=<token> python3 trae_checkin.py

幂等: 先查 status，已签到直接退出；claim 返回 10001 视为已签到。

设备指纹: claim 接口强制校验 x-device-id（aha 遥测 SDK 的数字设备 ID），
缺失或格式不对分别报 9004/9074。数字 ID 首次从 aha_electron 日志提取后缓存。
"""
import json
import os
import sys
import urllib.request
import urllib.error

API_BASE = 'https://api.trae.cn'
STATUS_PATH = '/trae/api/v2/ug/checkin_credits/status'
CLAIM_PATH = '/trae/api/v2/ug/checkin_credits/claim'
REGION = 'CN'
CODE_SUCCESS = 0
CODE_ALREADY_CHECKED = 10001


def get_device_id():
    did = os.environ.get('TRAE_DEVICE_ID', '').strip()
    if not did:
        print('ERROR 缺少 TRAE_DEVICE_ID（客户端日志里的数字型 deviceId，获取方法见 GUIDE.md）')
        sys.exit(1)
    return did


def get_headers(token):
    return {
        'Authorization': f'Cloud-IDE-JWT {token}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'X-User-Region': REGION,
        'x-device-id': get_device_id(),
        'x-device-brand': 'Mac',
        'x-device-type': 'macOS',
        'x-app-version': '3.4.3',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) trae/3.4.3 Chrome/140.0.0.0 Electron/37.0.0 Safari/537.36',
    }


def get_token():
    if os.environ.get('TRAE_JWT'):
        return os.environ['TRAE_JWT']
    tf = os.environ.get('TRAE_TOKEN_FILE', '/tmp/trae_auth_decrypted.json')
    if os.path.exists(tf):
        return json.load(open(tf))['token']
    print('ERROR 未找到 token：请设置 TRAE_JWT 环境变量或提供 TRAE_TOKEN_FILE')
    sys.exit(1)


def call(token, path):
    req = urllib.request.Request(
        API_BASE + path,
        data=json.dumps({'req_source': 1}).encode(), method='POST',
        headers=get_headers(token),
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
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
    print('查询签到状态...')
    code, status = call(token, STATUS_PATH)
    print('status HTTP', code, json.dumps(status, ensure_ascii=False))
    if code != 200:
        print('ERROR status 接口失败，token 可能过期')
        sys.exit(1)
    if status.get('did_checked_in'):
        print(f"SKIP 今日已签到（积分 {status.get('credits')}），无需重复")
        return
    if not status.get('enable'):
        print('ERROR 签到功能未开启')
        sys.exit(1)

    print('执行签到...')
    code, claim = call(token, CLAIM_PATH)
    print('claim HTTP', code, json.dumps(claim, ensure_ascii=False))
    biz = claim.get('code')
    if code == 200 and biz == CODE_SUCCESS:
        print(f"SUCCESS 签到成功，当前积分 {claim.get('credits', '?')}")
    elif biz == CODE_ALREADY_CHECKED:
        print('SKIP 今日已签到（claim 返回 10001），无需重复')
    else:
        print('ERROR 签到失败')
        sys.exit(1)


if __name__ == '__main__':
    main()
