# Tauri 桌面端（原生应用）

AI Interpreter 已提供 **Tauri v2** 桌面端骨架，摆脱浏览器、以原生窗口运行，
同时保留浏览器/Electron 两条既有启动路径。

## 特性

- **原生窗口**：Tauri WebView（Windows WebView2 / macOS WKWebView / Linux WebKitGTK），
  无需浏览器，安装包体积远小于 Electron（约 10-20MB）。
- **系统托盘**：最小化到托盘、点击恢复、菜单显示/退出。
- **单实例**：重复启动会聚焦已有窗口。
- **透明悬浮字幕窗**：独立 always-on-top 字幕窗口，覆盖在其它应用之上。
- **本地设置桥接**：通过 Tauri 命令读写 `config/desktop-settings.local.json`，
  与 Electron preload 接口对齐（密钥仅存存在性，不回传明文）。
- **内置终端**：xterm.js + 后端 PTY WebSocket 桥接（与浏览器端共用）。
- **系统音频采集（实验）**：`--features system-audio` 编译后可通过 cpal 抓取
  loopback 设备（需安装 BlackHole / VB-Audio Cable）；前端控制面板可在
  **麦克风 / 系统音频** 之间切换输入源，系统音频帧会自动下混为单声道并
  重采样到 16kHz 后送入翻译管线。
- **后端 TTS 语音播放**：译文 final 后由后端 edge-tts/OpenAI 合成 MP3 经
  WebSocket 下发，前端解码播放（不再依赖浏览器本地语音）；控制面板可选
  **自动 / 本地 / 服务端** 三种语音引擎。

## 目录结构

```
frontend/
├── src-tauri/              # Tauri v2 工程
│   ├── Cargo.toml
│   ├── tauri.conf.json
│   ├── capabilities/default.json
│   └── src/
│       ├── main.rs         # 入口
│       ├── lib.rs          # 托盘、单实例、悬浮窗、命令注册
│       ├── commands.rs     # 前端命令桥（设置/后端状态/悬浮窗）
│       ├── settings.rs     # 本地设置读写
│       └── audio_capture.rs# 系统音频 loopback（feature 门控）
└── src/                    # 复用 Web 前端（React + xterm + Lucide）
```

## 环境要求

- Node.js 20+（前端构建）
- Rust stable（Tauri 编译）
- 平台依赖：
  - **Windows**：WebView2 运行时（Win10/11 自带）
  - **macOS**：Xcode Command Line Tools
  - **Linux**：`webkit2gtk-4.1`、`gtk3`、`libsoup3`、`javascriptcoregtk-4.1` 等

```bash
# Debian/Ubuntu
sudo apt install libwebkit2gtk-4.1-dev build-essential curl wget file \
  libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev
```

## 启动（开发）

```bash
cd frontend
npm install
npm run tauri:dev
```

Tauri 会先运行 `beforeDevCommand`（`npm run dev` 启动 Vite），
再打开原生窗口。后端需另行启动：

```bash
cd backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

## 启动（通过统一 launcher）

`tools/desktop_launcher.py` 已支持 `--mode tauri`，会同时拉起
前端静态服务、后端 FastAPI 与 Tauri 窗口：

```bash
python tools/desktop_launcher.py --build --mode tauri
```

Windows 双击 `start-tauri.cmd` 即可。

## 构建安装包

```bash
cd frontend
npm run tauri:build
```

产物位于 `src-tauri/target/release/bundle/`（Linux 下生成 `.deb` / `.rpm` / `.AppImage`；
Windows 下生成 NSIS/MSI 安装包）。

**已验证（2026-08-08，Linux x86_64）**：

- `cargo check` 默认特性 + `--features system-audio` 均零警告通过
- `npm run tauri:build` 成功产出 3 个安装包：
  - `AI Interpreter_0.1.0_amd64.deb`（约 5.1MB，依赖 WebKitGTK/GTK3）
  - `AI Interpreter-0.1.0-1.x86_64.rpm`（约 5.1MB）
  - `AI Interpreter_0.1.0_amd64.AppImage`（约 96MB，自带运行时，免安装）
- Xvfb 无头环境冒烟启动：日志输出 `AI Interpreter Tauri setup complete`，托盘/悬浮窗/单实例初始化正常

## 系统音频采集（可选）

```bash
cd frontend/src-tauri
cargo build --features system-audio
```

构建后，前端在 **音频输入** 下拉中会出现「系统音频 (Tauri)」选项。

采集链路：

```
cpal loopback 设备
  → Rust 侧 `audio_capture.rs` 采集 float32 PCM
  → 通过 `audio:data` 事件（base64 + sampleRate + channels）推送前端
  → 前端 `src/desktop/system-audio.ts` 解码、下混为单声道、
    线性重采样到 16kHz
  → 复用 `WsClient.sendAudio` 送入后端翻译管线
```

此特性依赖本机 loopback 驱动（Windows Stereo Mix / macOS BlackHole /
Linux PulseAudio monitor），默认关闭。Rust 侧命令
`start_system_audio` / `stop_system_audio` / `get_system_audio_state`
已注册，前端可据此查询/控制采集状态。

## 语音引擎选择

控制面板「语音」区域新增引擎下拉：

| 引擎 | 行为 |
|------|------|
| 自动（优先服务端） | 默认。后端收到 `tts_audio` 即切到服务端 MP3 播放并停掉本地朗读 |
| 本地浏览器语音 | 始终用 `speechSynthesis` 流式朗读（低延迟，质量取决于系统语音） |
| 服务端 TTS | 只用后端 edge-tts/OpenAI 合成的 MP3 |

后端默认 `TTS_ENGINE=edge`（免费、无需 key）。关闭后端 TTS：
设置 `TTS_ENGINE=off`（`.env` 或环境变量）。

### Tauri 命令桥（前端可用）

编译 `--features system-audio` 后，前端可通过 `invoke` 调用：

| 命令 | 说明 |
|---|---|
| `start_system_audio` | 启动 loopback 采集，返回 `{active, device, sampleRate, channels}` |
| `stop_system_audio` | 停止采集 |
| `get_system_audio_status` | 查询采集状态 |

前端桥接层封装在 `src/desktop/tauri.ts`（`startTauriSystemAudio` / `stopTauriSystemAudio` /
`getTauriSystemAudioStatus`），事件监听 `audio:data` 即可拿到 base64 PCM 帧。

```ts
import { startTauriSystemAudio, stopTauriSystemAudio } from '../desktop/tauri'

const status = await startTauriSystemAudio()
// status.device: 'BlackHole 2ch' | 'VB-Audio Virtual Cable' | 'Monitor of ...'
```

> 注意：Linux 无头环境（CI/容器）没有 loopback 设备，启动会返回
> `未找到 loopback 音频设备` 错误 —— 这是预期行为，需在真实桌面机验证。

## 与 Electron 的差异

| 维度 | Electron | Tauri |
|------|----------|-------|
| 包体积 | ~150MB | ~10-20MB |
| 内存占用 | 较高 | 低 |
| 渲染内核 | Chromium | 系统 WebView |
| 前端复用 | 完全 | 完全 |
| 系统音频 | 需原生模块 | cpal（实验） |
| 生态成熟度 | 高 | 快速成长 |

建议：演示/兜底用 Electron，正式发布用 Tauri（体积与性能更优）。
