//! 前端命令桥接层。
//!
//! 提供 Tauri 命令，供前端通过 `@tauri-apps/api/core.invoke` 调用：
//! - 平台信息 / 后端进程管理（本地桌面模式下由 Python launcher 负责时返回占位状态）
//! - 本地设置读写（与 Electron preload 暴露的接口对齐）
//! - 悬浮字幕窗控制

use serde::Serialize;
use std::sync::Mutex;
use tauri::{AppHandle, Manager, State};

use crate::settings::{read_settings_snapshot, write_settings_update};

/// 平台信息（前端可据此决定是否展示 Tauri 特性入口）。
#[derive(Serialize)]
pub struct PlatformInfo {
    pub tauri: bool,
    pub os: String,
    pub arch: String,
}

/// 后端进程状态（桌面模式下由 Python launcher 托管，此处返回查询结果）。
#[derive(Serialize, Default)]
pub struct BackendStatus {
    pub running: bool,
    pub port: Option<u16>,
    pub managed_by_launcher: bool,
}

/// 悬浮窗状态。
#[derive(Serialize)]
pub struct OverlayState {
    pub available: bool,
    pub visible: bool,
}

/// 后端进程句柄（占位：桌面版进程由 Python launcher 派生，
/// Tauri 只负责窗口与托盘；保留结构便于后续内嵌后端演进）。
#[derive(Default)]
pub struct BackendProcess {
    pub child: Mutex<Option<std::process::Child>>,
}

/// 系统音频采集状态（前端查询用；仅 `system-audio` 特性编译时可用）。
#[derive(Serialize, Default)]
pub struct SystemAudioState {
    pub available: bool,
    pub capturing: bool,
    pub sample_rate: Option<u32>,
    pub channels: Option<u16>,
}

#[cfg(feature = "system-audio")]
pub mod sysaudio {
    use std::sync::Mutex;
    use tauri::{AppHandle, Manager};

    use super::SystemAudioState;

    /// 全局采集句柄：`audio_capture.rs` 的 SystemAudioCapture 在此管理。
    pub struct SystemAudioHandle {
        pub capture: Mutex<Option<crate::audio_capture::SystemAudioCapture>>,
    }

    impl Default for SystemAudioHandle {
        fn default() -> Self {
            Self {
                capture: Mutex::new(None),
            }
        }
    }

    pub fn start(app: &AppHandle) -> Result<(), String> {
        let state = app.state::<SystemAudioHandle>();
        let mut guard = state.capture.lock().map_err(|e| e.to_string())?;
        if guard.is_none() {
            let mut capture = crate::audio_capture::SystemAudioCapture::new();
            capture.start(app.clone())?;
            *guard = Some(capture);
        }
        Ok(())
    }

    pub fn stop(app: &AppHandle) -> Result<(), String> {
        let state = app.state::<SystemAudioHandle>();
        let mut guard = state.capture.lock().map_err(|e| e.to_string())?;
        if let Some(mut capture) = guard.take() {
            capture.stop();
        }
        Ok(())
    }

    pub fn status(app: &AppHandle) -> SystemAudioState {
        let state = app.state::<SystemAudioHandle>();
        let guard = state.capture.lock().unwrap_or_else(|e| e.into_inner());
        SystemAudioState {
            available: true,
            capturing: guard.is_some(),
            sample_rate: None,
            channels: None,
        }
    }
}

#[tauri::command]
pub fn get_platform() -> PlatformInfo {
    PlatformInfo {
        tauri: true,
        os: std::env::consts::OS.to_string(),
        arch: std::env::consts::ARCH.to_string(),
    }
}

#[tauri::command]
pub fn start_backend(state: State<'_, BackendProcess>) -> Result<BackendStatus, String> {
    // TODO(desktop): 由 launcher 负责后端启动；此处保留接口。
    let _ = state;
    Ok(BackendStatus {
        running: true,
        port: None,
        managed_by_launcher: true,
    })
}

#[tauri::command]
pub fn stop_backend(state: State<'_, BackendProcess>) -> Result<(), String> {
    let mut child = state.child.lock().map_err(|e| e.to_string())?;
    if let Some(mut process) = child.take() {
        let _ = process.kill();
        let _ = process.wait();
    }
    Ok(())
}

#[tauri::command]
pub fn get_backend_status() -> BackendStatus {
    BackendStatus {
        running: true,
        port: None,
        managed_by_launcher: true,
    }
}

#[tauri::command]
pub fn read_desktop_settings() -> Result<serde_json::Value, String> {
    read_settings_snapshot().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn save_desktop_settings(
    update: serde_json::Value,
) -> Result<serde_json::Value, String> {
    write_settings_update(update).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn set_overlay_visible(app: AppHandle, visible: bool) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("overlay") {
        if visible {
            let _ = window.show();
            let _ = window.set_focus();
        } else {
            let _ = window.hide();
        }
    }
    Ok(())
}

#[tauri::command]
pub fn get_overlay_state(app: AppHandle) -> OverlayState {
    let visible = app
        .get_webview_window("overlay")
        .map(|window| window.is_visible().unwrap_or(false))
        .unwrap_or(false);
    OverlayState {
        available: true,
        visible,
    }
}

/// 开始采集系统音频（loopback）。仅 `system-audio` 特性下有效，
/// 否则返回明确错误，前端据此隐藏/禁用入口。
#[tauri::command]
pub fn start_system_audio(app: AppHandle) -> Result<SystemAudioState, String> {
    #[cfg(feature = "system-audio")]
    {
        sysaudio::start(&app)?;
        Ok(sysaudio::status(&app))
    }

    #[cfg(not(feature = "system-audio"))]
    {
        let _ = app;
        Err("system-audio feature is not enabled in this build".to_string())
    }
}

/// 停止系统音频采集。
#[tauri::command]
pub fn stop_system_audio(app: AppHandle) -> Result<SystemAudioState, String> {
    #[cfg(feature = "system-audio")]
    {
        sysaudio::stop(&app)?;
        Ok(sysaudio::status(&app))
    }

    #[cfg(not(feature = "system-audio"))]
    {
        let _ = app;
        Err("system-audio feature is not enabled in this build".to_string())
    }
}

/// 查询系统音频采集状态。
#[tauri::command]
pub fn get_system_audio_state(app: AppHandle) -> SystemAudioState {
    #[cfg(feature = "system-audio")]
    {
        sysaudio::status(&app)
    }

    #[cfg(not(feature = "system-audio"))]
    {
        let _ = app;
        SystemAudioState {
            available: false,
            capturing: false,
            sample_rate: None,
            channels: None,
        }
    }
}
