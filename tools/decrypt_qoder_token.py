#!/usr/bin/env python3
"""解密 Qoder CN 客户端 auth.v1.dat 里的登录 token（Electron safeStorage 算法）。

算法: AES-128-CBC
  密钥派生: PBKDF2-SHA1(password=keychain密码, salt="saltysalt", iterations=1003, dklen=16)
  IV: 16 字节 0x20
  密文布局: [3字节"v10"前缀][AES密文]
  明文为 JSON: { token, refreshToken, expiresAt, refreshTokenExpiresAt, user }

用法:
  python3 decrypt_qoder_token.py            # 打印 token 信息
  python3 decrypt_qoder_token.py --stdout   # 仅输出 token（供 sync 脚本读取）
  python3 decrypt_qoder_token.py --pbcopy   # 复制 token 到剪贴板
"""
import hashlib
import json
import os
import subprocess
import sys

KEYCHAIN_SERVICE = 'Qoder CN App Safe Storage'
AUTH_FILE = os.path.expanduser('~/Library/Application Support/com.qodercn.app.stable/auth.v1.dat')
PBKDF2_SALT = b'saltysalt'
PBKDF2_ITER = 1003
PBKDF2_DKLEN = 16
AES_IV = bytes([0x20] * 16)


def get_keychain_password():
    """从 macOS 钥匙串获取 Electron safeStorage 加密密码。"""
    try:
        return subprocess.check_output(
            ['security', 'find-generic-password', '-s', KEYCHAIN_SERVICE, '-w'],
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError:
        print(f'ERROR 未找到钥匙串条目 "{KEYCHAIN_SERVICE}"，请先启动并登录 Qoder CN 客户端')
        sys.exit(1)


def decrypt(auth_path):
    """解密 auth.v1.dat，返回包含 token 等字段的 dict。"""
    if not os.path.exists(auth_path):
        print(f'ERROR 凭据文件不存在: {auth_path}')
        print('请先启动并登录 Qoder CN 客户端')
        sys.exit(1)

    pw = get_keychain_password()
    data = open(auth_path, 'rb').read()
    if data[:3] != b'v10':
        print(f'ERROR 未知的加密前缀: {data[:3]}')
        sys.exit(1)

    ciphertext = data[3:]
    key = hashlib.pbkdf2_hmac('sha1', pw, PBKDF2_SALT, PBKDF2_ITER, dklen=PBKDF2_DKLEN)

    proc = subprocess.Popen(
        ['openssl', 'enc', '-d', '-aes-128-cbc', '-K', key.hex(), '-iv', AES_IV.hex()],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    plain, err = proc.communicate(ciphertext)
    if proc.returncode != 0:
        print(f'ERROR AES 解密失败: {err.decode()}')
        sys.exit(1)

    # PKCS7 去填充
    pad_len = plain[-1]
    if 1 <= pad_len <= 16:
        plain = plain[:-pad_len]

    return json.loads(plain)


def main():
    auth_path = AUTH_FILE
    for i, arg in enumerate(sys.argv):
        if arg == '--auth-file' and i + 1 < len(sys.argv):
            auth_path = sys.argv[i + 1]

    auth = decrypt(auth_path)
    token = auth.get('token', '')
    if not token:
        print('ERROR 解密成功但未找到 token 字段')
        sys.exit(1)

    if '--stdout' in sys.argv:
        print(token)
        return

    print('token 长度:', len(token))
    print('token 前缀:', token[:8] + '...')
    print('过期时间:', auth.get('expiresAt'))
    print('refresh 过期:', auth.get('refreshTokenExpiresAt'))

    if '--pbcopy' in sys.argv:
        subprocess.run(['pbcopy'], input=token.encode())
        print('已复制到剪贴板')


if __name__ == '__main__':
    main()
