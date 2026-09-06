# 部署与运维指南（Deployment & Operations）

> 适用产品：AI 同声传译助手（competition2）

本文档覆盖从本地开发到生产部署的完整运维路径，包括环境准备、配置、
构建、部署形态、健康检查、成本控制与故障排查。

---

## 一、产品形态概览

| 形态 | 说明 | 入口 |
|---|---|---|
| 桌面应用（推荐） | Tauri 原生桌面端，摆脱浏览器 | `start-tauri.cmd` / `tauri dev` |
| 本地 Web | 后端 + 前端 + 浏览器访问 | `start-web.cmd` / launcher |
| 云端 SaaS（远期） | 多用户多会话托管 | 需补充账号体系后启用 |

---

## 二、环境准备

### 后端（Python 3.11+）

```bash
cd backend
pip install -r requirements.txt
# 复制模板并填入真实 key
cp .env.example .env.local
```

### 前端（Node 20+）

```bash
cd frontend
npm install
npm run build        # 产物在 dist/
```

### 桌面端（Tauri，可选）

需安装 Rust 工具链及系统依赖（GTK/ALSA 等），见 `docs/TAURI_DESKTOP.md`。

### Redis

```bash
# 本地单机
redis-server
# 或使用 docker-compose
docker compose up -d
```

---

## 三、核心配置

全部通过环境变量 / `.env.local` 配置（模板见 `backend/.env.example`）：

| 配置项 | 说明 | 默认值 |
|---|---|---|
| `HOST` | 监听地址（默认本机回环） | `127.0.0.1` |
| `ASR_ENGINE` | `openai`（远程）或 `whisper`（本地） | `openai` |
| `NMT_ENGINE` | `claude` / `openai` | `claude` |
| `TTS_ENGINE` | `edge` / `openai` / `off` | `edge` |
| `SUBSCRIPTION_PLAN` | 默认套餐 | `free` |
| `COST_NMT_INPUT_PER_M` / `COST_NMT_OUTPUT_PER_M` | NMT 单价（美元/M） | `0.15` / `0.60` |
| `COST_DAILY_LIMIT_USD` | 每日成本软上限（美元） | `2.0` |

---

## 四、部署形态

### 4.1 本地桌面 / 单机部署（默认）

```bash
python backend/main.py
# 前端 build 后由 launcher 或 Tauri 加载
```

### 4.2 局域网 / 服务器部署

> ⚠️ 将 `HOST` 改为非回环地址会暴露服务，**务必先配置鉴权**。

```bash
HOST=0.0.0.0 ALLOWED_ORIGINS=<前端来源> python backend/main.py
```

### 4.3 Docker 编排（开发/演示）

```bash
docker compose up -d
```

---

## 五、健康检查与监控

### 健康端点

```
GET /api/v1/health
```

### 会话诊断

运行中的会话通过 WebSocket 周期下发诊断信息（延迟、丢包、队列深度、
修正计数）。会话结束后质量指标随会话台账落盘，可在历史面板回看。

### 成本监控

```
GET /api/v1/cost        # 用量 + 估算成本 + 熔断建议
POST /api/v1/cost/reset # 清空累计（管理用）
```

当日估算成本达到 `COST_DAILY_LIMIT_USD` 时，成本面板会给出降级建议
（切换本地 Whisper / 更低规格 NMT 模型）。

### 翻译质量回归

```bash
python tools/eval_translation_quality.py --pair-file refs.csv --json
```

对人工参考译文跑轻量 BLEU，可持续跟踪翻译质量波动。

---

## 六、成本控制最佳实践

1. **优先本地 Whisper**：`ASR_ENGINE=whisper` 消除 ASR 音频上传成本。
2. **开启翻译记忆库**（默认开启）：相似句直接复用译文，省 NMT 调用。
3. **开启术语热词 + ASR 后处理**：降低误识别与重复修正，减少无效 API 调用。
4. **设置成本软上限**：用 `COST_DAILY_LIMIT_USD` 监控成本异常。
5. **控制修正频率**：`REVISION_MAX_TOTAL` 限制单会话修正总次数防成本失控。

---

## 七、安全基线（上线前必查）

- [ ] 默认 `HOST=127.0.0.1`，公网暴露前已配置鉴权
- [ ] `.env.local` 未入库（`.gitignore` 已覆盖）
- [ ] CORS 白名单精确（无 `*`）
- [ ] 本地设置/密钥文件权限为 `0600`
- [ ] 明确对外隐私政策（见 `PRIVACY.md`）

---

## 八、故障排查

| 现象 | 排查方向 |
|---|---|
| 无字幕 | 检查 ASR/NMT 是否有 key、网络连通性、降级日志 |
| 延迟高 | 本地 Whisper CPU 模型慢；换 GPU / 远程 ASR |
| 成本异常 | 查看 `/api/v1/cost` 用量，确认是否漏配记忆库 |
| 记忆库不生效 | 确认 `TRANSLATION_MEMORY_ENABLED=true` |
| 桌面端打不开 | 见 `docs/TAURI_DESKTOP.md` 依赖清单 |

---

*最后更新：2026-08-10*
