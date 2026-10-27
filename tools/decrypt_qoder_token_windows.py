#!/usr/bin/env python3
"""Windows 版 Qoder 客户端 token 提取（替代 macOS 专用的 decrypt_qoder_token.py）。

Windows 上 Electron safeStorage 走 Chromium os_crypt：
  Local State → os_crypt.encrypted_key → base64 → 去掉 "DPAPI" 头 →
  CryptUnprotectData（DPAPI，绑定当前 Windows 用户）→ 32 字节 AES-256 key
  auth.v1.dat → [3 字节 "v10"/"v20"][12 字节 nonce][密文 + 16 字节 GCM tag]

老版本 Electron 也可能是「整个文件直接 DPAPI」，脚本按多种方案依次尝试。

依赖: pip install cryptography

用法:
  python tools/decrypt_qoder_token_windows.py --peek     # 只看结构和解密方案，绝不输出 token
  python tools/decrypt_qoder_token_windows.py            # 长度 / 前缀 / 过期时间
  python tools/decrypt_qoder_token_windows.py --stdout   # 仅输出 token（供管道传给 gh secret set）

安全: token 只在 --stdout 时打印到 stdout，其余模式仅输出长度与前 5 字符。
"""
import argparse
import base64
import ctypes
import json
import os
import sys
from ctypes import wintypes

APP_NAME = 'com.qoder.app.stable'


def default_path(filename):
    appdata = os.environ.get('APPDATA') or os.path.expanduser('~/AppData/Roaming')
    return os.path.join(appdata, APP_NAME, filename)


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ('cbData', wintypes.DWORD),
        ('pbData', ctypes.POINTER(ctypes.c_char)),
    ]


def dpapi_unprotect(blob):
    """CryptUnprotectData：只能被加密时的那个 Windows 用户解开。"""
    if not blob:
        raise ValueError('空数据')
    buf = ctypes.create_string_buffer(blob, len(blob))
    blob_in = DATA_BLOB(len(blob), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    )
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def os_crypt_key(local_state_path):
    """从 Local State 取出 DPAPI 保护的 AES-256 key。"""
    with open(local_state_path, 'r', encoding='utf-8-sig') as f:
        state = json.load(f)
    encrypted_raw = state.get('os_crypt', {}).get('encrypted_key')
    if not encrypted_raw:
        raise ValueError('Local State 里没有 os_crypt.encrypted_key（该客户端可能不用 os_crypt）')
    encrypted = base64.b64decode(encrypted_raw)
    if encrypted[:5] != b'DPAPI':
        raise ValueError('encrypted_key 缺少 DPAPI 前缀')
    key = dpapi_unprotect(encrypted[5:])
    if len(key) != 32:
        raise ValueError(f'os_crypt key 长度异常: {len(key)}（期望 32）')
    return key


def aesgcm_decrypt(key, data):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce, ciphertext = data[:12], data[12:]
    if len(nonce) != 12:
        raise ValueError('nonce 长度不足')
    return AESGCM(key).decrypt(nonce, ciphertext, None)


def looks_like_auth_json(plain):
    try:
        obj = json.loads(plain)
    except Exception:
        return None
    if isinstance(obj, dict) and (obj.get('token') or obj.get('refreshToken')):
        return obj
    return None


def extract(auth_bytes, local_state_path):
    """依次尝试多种 Windows safeStorage 方案，返回 (auth_dict, 方案名, 失败原因列表)。"""
    failures = []

    try:
        key = os_crypt_key(local_state_path)
    except Exception as e:
        key = None
        failures.append(f'os_crypt key: {type(e).__name__}: {e}')

    has_prefix = auth_bytes[:3] in (b'v10', b'v20')
    version = auth_bytes[:3].decode('latin-1') if has_prefix else None
    body = auth_bytes[3:] if has_prefix else None

    if key and body is not None:
        label = f'{version} + AES-256-GCM(os_crypt)'
        try:
            obj = looks_like_auth_json(aesgcm_decrypt(key, body))
            if obj:
                return obj, label, failures
            failures.append(f'{label}: 解出内容但不是 auth JSON')
        except Exception as e:
            failures.append(f'{label}: {type(e).__name__}: {e}')

    # 老版本 Electron：整个文件直接 DPAPI 保护
    for label, data in (('整文件 DPAPI', auth_bytes), ('去前缀后 DPAPI', body)):
        if data is None:
            continue
        try:
            obj = looks_like_auth_json(dpapi_unprotect(data))
            if obj:
                return obj, label, failures
            failures.append(f'{label}: 解出内容但不是 auth JSON')
        except Exception as e:
            failures.append(f'{label}: {type(e).__name__}: {e}')

    return None, None, failures


def main():
    p = argparse.ArgumentParser(description='提取 Windows Qoder 登录 token')
    p.add_argument('--auth-file', default=default_path('auth.v1.dat'))
    p.add_argument('--local-state', default=default_path('Local State'))
    p.add_argument('--stdout', action='store_true', help='仅输出 token')
    p.add_argument('--peek', action='store_true', help='只打印结构信息，连前缀都不打印')
    args = p.parse_args()

    if sys.platform != 'win32':
        print('ERROR 本脚本只在 Windows 运行（DPAPI 是 Windows API）')
        sys.exit(1)

    for path in (args.auth_file, args.local_state):
        if not os.path.exists(path):
            print(f'ERROR 文件不存在: {path}')
            print('请确认已安装并登录过 Qoder 客户端')
            sys.exit(1)

    with open(args.auth_file, 'rb') as f:
        raw = f.read()
    auth, scheme, failures = extract(raw, args.local_state)

    if args.peek:
        print('auth 文件大小:', len(raw), '字节')
        print('前 3 字节:', repr(raw[:3]))
        print('解密方案:', scheme or '全部方案失败')
        print('字段:', sorted(auth.keys()) if auth else '(未解密，不显示任何值)')
        for f in failures:
            print('  尝试:', f)
        return 0 if auth else 1

    if not auth:
        print('ERROR 所有解密方案都失败')
        print(f'  auth 文件: {args.auth_file}（{len(raw)} 字节，前缀 {raw[:3]!r}）')
        for f in failures:
            print('  尝试:', f)
        print('  可能原因: Qoder 未登录、客户端换了加密方案、或当前 Windows 用户与登录时不是同一个')
        return 1

    token = auth.get('token', '')
    if not token:
        print('ERROR 解密成功但没有 token 字段，字段为:', sorted(auth.keys()))
        return 1

    if args.stdout:
        sys.stdout.write(token)
        return 0

    print('解密方案:', scheme)
    print('token 长度:', len(token))
    print('token 前缀:', token[:5] + '...')
    print('是否 CN 侧 token(dt- 开头):', '是' if token.startswith('dt-') else '否')
    print('过期时间:', auth.get('expiresAt'))
    print('refresh 过期:', auth.get('refreshTokenExpiresAt'))
    print('字段:', sorted(auth.keys()))
    return 0


if __name__ == '__main__':
    sys.exit(main())
