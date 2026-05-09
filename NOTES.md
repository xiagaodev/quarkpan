# 夸克网盘上传注意事项

> 整理自 2026-05-09 批量上传实践

---

## 1. Cookie 登录与会话

### 二维码登录（推荐）
```python
from quark_client.auth.api_login import APILogin
api = APILogin()
token, url = api.get_qr_code()          # 生成二维码
result = api.wait_for_login(token)       # 等待扫码确认，返回 service_ticket
```

**判断登录成功的关键**：必须 `service_ticket` 非空才算完成，仅 `status=1`（已扫码但未确认）不等于登录成功。

### Cookie 获取
二维码确认后，用 `service_ticket` 换取会话 Cookie：
```python
import httpx
client = httpx.Client(timeout=30.0)
resp = client.get(f'https://pan.quark.cn/account/info?st={service_ticket}&lw=scan')
cookie_str = '; '.join(f'{k}={v}' for k, v in client.cookies.items())
```

### Cookie 存储
- 有效期间可重复使用，无需每次重新扫码
- 存储路径：`config/cookies.txt`（不纳入 Git）
- 格式：标准 Cookie 字符串，`key=value; key=value...`

---

## 2. 文件上传要点

### 上传 API 调用
```python
from quark_client import QuarkClient
client = QuarkClient(cookies=cookie_str, auto_login=False)
client.upload_file('/path/to/file.pdf', parent_folder_id='目标文件夹fid')
```

### 分片上传（大文件 > 20MB）
- 夸克对大文件自动分片（每片 5MB）
- `parallel_upload=False` 更稳定（参考 quarkpan-rs 的实现）
- 分片后需按顺序调用 `/quark/login/send service token` 获取上传地址

### OSS 上传地址
- 从预上传接口返回的 `upload_url` 字段获取
- 注意：`upload_url` 可能返回 `http://pds.quark.cn`，需要**去掉 `http://` 前缀**，使用 `ul-zb.pds.quark.cn` 子域名（`pds.quark.cn` 本身无法解析）
- 上传路径：`https://ul-zb.pds.quark.cn/{obj_key}?partNumber={n}&uploadId={upload_id}`

### 已知 Bug 与修复
| 文件 | 问题 | 修复 |
|------|------|------|
| `file_upload_service.py` | 6 处上传逻辑错误 | 参考 `quarkpan-rs` 对齐参数 |
| `api_login.py` | `_is_login_success` 误判"已扫码"为"登录成功" | 必须 `service_ticket` 非空才算成功 |

---

## 3. 批量上传脚本

使用通用上传脚本 `upload.py`：

```bash
# 平铺上传（所有 PDF 直接进目标文件夹）
python3 upload.py <源目录> --target <目标fid>

# 保持一级目录结构上传
python3 upload.py <源目录> --target <目标fid> --keep-structure

# 指定子目录作为结构根目录
python3 upload.py <源目录> --target <目标fid> --keep-structure --structure-from printkids

# 调整并行数（默认4）
python3 upload.py <源目录> --target <目标fid> --workers 6

# 指定 Cookie 文件
python3 upload.py <源目录> --target <目标fid> --cookie config/cookies.txt
```

### 参数说明

| 参数 | 说明 |
|------|------|
| `source_dir` | 源目录（任意包含 PDF 的目录） |
| `--target` | 夸克网盘目标文件夹 fid（必填） |
| `--keep-structure` | 以源目录的顶层子文件夹分组上传，不会深挖嵌套目录 |
| `--structure-from` | 指定子目录作为结构根目录 |
| `--workers` | 并行上传数，默认 4 |
| `--cookie` | Cookie 文件路径，默认 `config/cookies.txt` |

### 同名冲突处理
脚本会自动检测文件夹是否已存在——若创建时遇到同名冲突，会自动重新查询已有文件夹的 fid，不会重复创建。

---

## 4. 并行上传

- `ThreadPoolExecutor(max_workers=4)` 并行上传 654 个文件约 5 分钟
- 每个文件耗时约 1.5-2s（含网络 + API 开销）
- 建议 `max_workers=4`，过高可能被限流

---

## 5. Git 管理

```
# .gitignore
downloads/           # 原始 PDF 文件（太大）
quark_env/           # Python 虚拟环境
config/              # 配置文件（含 cookie）
*.pyc
__pycache__/
*.log
```

### 仓库地址
```
https://github.com/xiagaodev/quarkpan
```

---

## 6. 项目结构
```
~/projects/netdisk-promotion/xianyu/
├── upload.py              # 通用批量上传脚本
├── downloader.py          # PDF 下载脚本
├── quark_client/          # 夸克网盘 Python SDK（基于 lich0821/QuarkPan）
│   ├── auth/
│   │   └── api_login.py           # 二维码登录（含修复）
│   └── services/
│       └── file_upload_service.py  # 文件上传（含修复）
├── config/
│   └── cookies.txt        # 登录 Cookie（不纳入 Git）
├── downloads/             # 待上传的 PDF 资源（不纳入 Git）
├── quark_env/             # Python 虚拟环境（不纳入 Git）
├── urls.json              # 资源 URL 列表
└── NOTES.md               # 本文档
```

### 工作区根目录
```
~/projects/netdisk-promotion/
├── xianyu/                # 闲鱼资源项目（夸克网盘）
└── ...其他网盘推广项目
```

---

## 7. 常见错误处理

| 错误信息 | 原因 | 处理 |
|----------|------|------|
| `HTTP 400: file is doloading[同名冲突]` | 文件/文件夹已存在 | 跳过或删除后重建 |
| `Name or service not known` (pds.quark.cn) | DNS 解析失败 | 使用 `ul-zb.pds.quark.cn` |
| `'QuarkClient' object has no attribute 'delete_file'` | 方法名错误 | 改用 `delete_files`（批量） |
| `service_ticket is None` | 二维码扫描后未确认 | 用户需在 App 内点击确认 |
