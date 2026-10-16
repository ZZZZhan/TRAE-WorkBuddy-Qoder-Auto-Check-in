# 云端签到部署指引（AI 执行）

用户把本仓库链接给了你并要求部署。请阅读本章，按序执行。

## 章节

| 章节 | 何时执行 |
|------|---------|
| 一、部署 | 首次部署 |
| 二、准点触发 | 需要准点执行时 |
| 三、token 自动同步（macOS） | 部署后，消除手动续 token |
| 四、token 自动同步（Windows） | 同三，Windows |

## 背景

- 签到脚本由 GitHub Actions 云端执行
- Secrets：`TRAE_JWT`、`TRAE_DEVICE_ID`、`WORKBUDDY_ACCESS_TOKEN`、`WORKBUDDY_UID`、`QODER_TOKEN`
- token 寿命：TRAE 约 7 天，WorkBuddy 约 28 天，Qoder 约 30 天

---

## 一、部署

### 前置确认

1. 确认产品：用户提示词已说明则按其执行；未说明则询问用户：TRAE / WorkBuddy / 两者
2. 登录态检查（仅检查所选产品）。文件未找到时依次执行：① `mdfind`/`where /r` 或文件名全盘搜索定位实际路径；② 仍找不到则询问用户是否登录过该客户端。

| 产品 | 标准路径 | 缺失时 |
|------|---------|-------|
| WorkBuddy | macOS：`~/Library/Application Support/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info`；Windows：`%LOCALAPPDATA%\CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info`（未命中再试 `%APPDATA%` 同级路径） | `open -a "WorkBuddy"`（Win：`start WorkBuddy`），等用户登录 |
| TRAE | macOS：`~/Library/Application Support/TRAE SOLO CN/User/globalStorage/storage.json`；Windows：`%APPDATA%\TRAE SOLO CN\User\globalStorage\storage.json`。含 `iCubeAuthInfo` 条目 | `open -a "TRAE SOLO CN"`，等用户登录 |

3. `gh auth status`；未登录执行 `gh auth login`

### 步骤

1. `gh repo fork <本仓库地址> --clone`（TRAE 需本地克隆，提取工具在 `tools/decrypt_trae_token.py`）
2. 提取凭证（macOS 用 `python3`，Windows 用 `python`）：

   WorkBuddy：
   ```bash
   python -c "import json; d=json.load(open(r'<登录态检查定位到的实际路径>')); print('WORKBUDDY_ACCESS_TOKEN='+d['auth']['accessToken']); print('WORKBUDDY_UID='+d['account']['uid'])"
   ```

   TRAE：
   ```bash
   python <克隆目录>/tools/decrypt_trae_token.py --stdout    # TRAE_JWT
   ```
   `TRAE_DEVICE_ID`：在 `~/Library/Application Support/TRAE SOLO CN/logs/<日期目录>/sharedprocess.log`（Windows：`%APPDATA%\TRAE SOLO CN\logs\`）搜 `"deviceId":"数字串"`；搜不到则全盘搜 `deviceId` 或询问用户

3. 写入 Secrets：
   ```bash
   printf '%s' "<值>" | gh secret set <名称> --repo <用户名>/<仓库名>
   ```
   token 仅进 Secrets，不落盘

4. `gh workflow run workbuddy_checkin.yml --repo <用户名>/<仓库名>`（TRAE 用 `trae_checkin.yml`），`gh run watch` 至完成

### 验收

- Secrets 全部创建
- workflow 运行 success，输出"签到成功"或"今日已签"
- 无 401/403

### 异常处理

| 现象 | 处理 |
|------|------|
| 凭证文件不存在 | 执行前置确认第 2 步登录流程 |
| TRAE 报 9004 | `TRAE_DEVICE_ID` 缺失或非纯数字 |
| TRAE 报 9074 | 设备 ID 值错误，重查日志 |
| WorkBuddy 400 `code:10001` | 今日已签，正常 |
| 401/403 | token 过期，重新提取更新 Secrets |

---

## 二、准点触发

原生 schedule 为 best-effort，用 cron-job.org 定时调 `workflow_dispatch` API。

### 前置

本步骤需浏览器自动化能力（注册页为 React SPA）。

### 步骤

1. 浏览器自动化打开 `https://console.cron-job.org/signup`，填用户邮箱，生成 16 位密码告知用户保存
2. 用户激活后登录，Settings → API Keys → 创建并记录 Key
3. 创建任务（`PUT https://api.cron-job.org/jobs`，认证 `Authorization: Bearer <APIKEY>`，文档 `https://docs.cron-job.org/rest-api.html`）：

   ```json
   {
     "job": {
       "title": "<任务名>",
       "url": "https://api.github.com/repos/<用户名>/<仓库>/actions/workflows/<workflow文件名>/dispatches",
       "enabled": true,
       "saveResponses": true,
       "requestMethod": 1,
       "requestTimeout": 60,
       "extendedData": {
         "headers": {
           "Authorization": "token <gh auth token 输出，部署阶段已登录无需单独创建>",
           "Content-Type": "application/json",
           "User-Agent": "cron-job-bridge"
         },
         "body": "{\"ref\":\"main\"}"
       },
       "schedule": {
         "timezone": "Asia/Shanghai",
         "expiresAt": 0,
         "hours": [10],
         "mdays": [-1],
         "minutes": [13],
         "months": [-1],
         "wdays": [-1]
       },
       "notification": { "onFailure": true, "onSuccess": false, "onDisable": true }
     }
   }
   ```

   每个产品两个任务：主签 10:13 / 10:23，兜底 16:07 / 16:17。JSON 写入脚本文件执行。

### 验收

- `GET /jobs` 返回任务，`enabled: true`
- GitHub dispatch API 返回 204
- 到点后 history 含 `httpStatus: 204`，GitHub Actions 同分钟出现新运行

### 异常处理

| 现象 | 处理 |
|------|------|
| 注册页提交无响应 | React SPA，用真实浏览器自动化 |
| PAT 更换 | 更新任务 Authorization 头 |

---

## 三、token 自动同步（macOS）

### 生成内容

1. `sync_tokens.sh`：
   - `unset PYTHONHOME PYTHONPATH`
   - 读 WorkBuddy token（路径见第一章前置确认）
   - `python3 <项目目录>/tools/decrypt_trae_token.py --stdout` 取 TRAE token
   - `printf '%s' "$TOKEN" | gh secret set <名称> --repo <用户名>/<仓库>`
   - 输出追加 `token_sync.log`，带时间戳；失败仅记日志不重试，未读到 token 记 ERROR 退出
   - 需代理时 export `HTTPS_PROXY`/`HTTP_PROXY`
2. `~/Library/LaunchAgents/com.token-sync.daily.plist`：`StartCalendarInterval` 每日 09:30，`/bin/bash` 执行
3. `launchctl bootstrap gui/$(id -u) <plist路径>`

### 验收

- 手动执行一次，Secrets 更新，日志含"已更新（N 字符）"
- `launchctl list | grep token-sync` 有任务
- 日志不含 token 值

### 异常处理

| 现象 | 处理 |
|------|------|
| launchd 缺 PATH | 脚本内 `export PATH`（含 gh） |
| python3 报 encodings 错误 | `PYTHONHOME` 被继承，确认 unset |
| gh 卡 TLS 握手超时 | 代理未启动 |

---

## 四、token 自动同步（Windows）

### 生成内容

1. `sync_tokens.ps1`：
   - 读 WorkBuddy token：`%LOCALAPPDATA%\CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info`（未命中再试 `%APPDATA%` 同级路径）
   - `python tools/decrypt_trae_token.py --stdout` 取 TRAE token（路径不同加 `--storage`）
   - `gh secret set <名称> --repo <用户名>/<仓库>`（stdin 传入）
   - 写 `token_sync.log`；失败仅记录不重试，未读到 token 记 ERROR 退出
2. `schtasks /create /sc daily` 每日 09:30 执行

### 验收

- 手动执行一次，Secrets 更新
- 任务计划程序存在每日任务
- token 不出现在命令行参数或临时文件
