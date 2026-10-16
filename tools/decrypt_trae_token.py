#!/usr/bin/env python3
"""解密 TRAE SOLO CN 客户端 storage.json 里的登录 token（byteCrypto 算法复刻）。

算法: AES-128-CBC
  密文布局: [6字节版本头][32字节随机key][AES密文]
  AES key/iv 派生: SHA-512( SHA-512(randomKey) + XOR_KEY_TABLE ) 的前16/次16字节
  明文布局: [64字节SHA-512校验头][实际JSON]
密钥表从 TRAE SOLO CN.app/Contents/Resources/app/out/main.js 提取（byteCrypto.js 模块）。

用法:
  python3 decrypt_trae_token.py            # 打印 token 信息
  python3 decrypt_trae_token.py --pbcopy   # 复制 token 到剪贴板
"""
import base64
import glob
import hashlib
import json
import os
import subprocess
import sys

# main.js byteCrypto.js 模块里的 XOR 密钥表（AES 版本）
K1 = bytes([82,9,106,213,48,54,165,56,191,64,163,158,129,243,215,251,124,227,57,130,155,47,255,135,52,142,67,68,196,222,233,203,84,123,148,50,166,194,35,61,238,76,149,11,66,250,195,78,8,46,161,102,40,217,36,178,118,91,162,73,109,139,209,37])
K2 = bytes([31,221,168,51,136,7,199,49,177,18,16,89,39,128,236,95,96,81,127,169,25,181,74,13,45,229,122,159,147,201,156,239,160,224,59,77,174,42,245,176,200,235,187,60,131,83,153,97,23,43,4,126,186,119,214,38,225,105,20,99,85,33,12,125])

QM, BH, IO, FV = 6, 64, 64, 32
STORAGE_CANDIDATES = [
    # 2026-10 合并升级后新应用优先
    os.path.expanduser('~/Library/Application Support/Trae CN/User/globalStorage/storage.json'),
    os.path.expanduser('~/Library/Application Support/TRAE SOLO CN/User/globalStorage/storage.json'),
]

def sha512(b):
    return hashlib.sha512(b).digest()


def xor_table(t):
    return bytes(K1[i] ^ K2[i] for i in range(t))


def derive_key_iv(random_key32):
    n = bytearray(BH + IO)
    n[0:BH] = sha512(random_key32)
    n[BH:BH + IO] = xor_table(IO)
    n[0:BH + IO] = sha512(bytes(n))
    return bytes(n[0:16]), bytes(n[16:32])


def decrypt(b64str):
    data = base64.b64decode(b64str)
    if data[0] != 116 or data[1] != 99:
        raise ValueError(f'unknown version header: {list(data[0:6])}')
    random_key = data[QM:QM + FV]
    aes_key, iv = derive_key_iv(random_key)
    body = data[FV + QM:]
    with subprocess.Popen(
        ['openssl', 'enc', '-d', '-aes-128-cbc', '-K', aes_key.hex(), '-iv', iv.hex()],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    ) as p:
        plain, _ = p.communicate(body)
    mac, payload = plain[:BH], plain[BH:]
    if sha512(payload) != mac:
        raise ValueError('SHA-512 校验失败，数据可能损坏')
    return payload


def main():
    storage = next((p for p in STORAGE_CANDIDATES if os.path.exists(p)), STORAGE_CANDIDATES[0])
    for i, arg in enumerate(sys.argv):
        if arg == '--storage' and i + 1 < len(sys.argv):
            storage = sys.argv[i + 1]
    d = json.load(open(storage))
    entries = {k: v for k, v in d.items() if k.startswith('iCubeAuthInfo://')}
    if not entries:
        print('ERROR 未找到 iCubeAuthInfo 条目，请先登录 TRAE SOLO CN 客户端')
        sys.exit(1)
    auth = None
    for k, v in entries.items():
        obj = json.loads(decrypt(v))
        if 'token' in obj:
            auth = obj
            print(f'命中 {k}')
            break
    if not auth:
        print('ERROR 解密成功但未找到 token 字段')
        sys.exit(1)
    if '--stdout' in sys.argv:
        print(auth['token'])
        return
    print('token 长度:', len(auth['token']))
    print('过期时间:', auth.get('expiredAt'))
    print('refresh 过期:', auth.get('refreshExpiredAt'))
    if '--pbcopy' in sys.argv:
        subprocess.run(['pbcopy'], input=auth['token'].encode())
        print('已复制到剪贴板，去 GitHub Secrets 更新 TRAE_JWT 即可')


if __name__ == '__main__':
    main()
