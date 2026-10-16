# TRAE-WorkBuddy-Qoder 自动签到

云端自动签到 Trae、WorkBuddy 和 Qoder CN 的每日积分/credits。

## 签到时间

| 产品 | 北京时间 | 说明 |
|------|---------|------|
| WorkBuddy | 10:13 | codebuddy.cn |
| TRAE | 10:23 | api.trae.cn |
| Qoder CN | 10:33 | openapi.qoder.com.cn |

每个产品另有一次下午兜底运行。

## 文件结构

```
├── trae_checkin.py              # TRAE 签到
├── workbuddy_checkin.py         # WorkBuddy 签到
├── qoder_checkin.py             # Qoder CN 签到
├── tools/
│   ├── decrypt_trae_token.py    # TRAE token 解密（byteCrypto AES-128-CBC）
│   └── decrypt_qoder_token.py   # Qoder token 解密（Electron safeStorage）
├── .github/workflows/
│   ├── trae_checkin.yml
│   ├── workbuddy_checkin.yml
│   └── qoder_checkin.yml
└── GUIDE.md
```

## Secrets

| 名称 | 说明 |
|------|------|
| `TRAE_JWT` | TRAE 登录 token（约 7 天有效期） |
| `TRAE_DEVICE_ID` | TRAE 设备指纹 ID |
| `WORKBUDDY_ACCESS_TOKEN` | WorkBuddy JWT（约 28 天有效期） |
| `WORKBUDDY_UID` | WorkBuddy 用户 ID |
| `QODER_TOKEN` | Qoder CN 登录 token（约 30 天有效期） |
