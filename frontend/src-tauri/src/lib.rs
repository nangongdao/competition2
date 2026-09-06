//! AI Interpreter Tauri 桌面端。
//!
//! 职责：
//! - 主窗口 + 透明悬浮字幕窗（overlay）
//! - 系统托盘（显示/隐藏主窗口、退出）
//! - 单实例锁（重复启动聚焦已有窗口）
//! - 前端命令桥接（后端进程管理、本地设置读写、悬浮窗控制）
//! - 可选系统音频 loopback 采集（feature: system-audio，默认关闭）

mod audio_capture;
mod commands;
mod settings;

use log::info;
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Manager, Runtime,
};

pub const OVERLAY_EVENT: &str = "overlay:snapshot";

/// 应用初始化：注册插件、托盘、单实例。
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_log::Builder::new().build())
        .plugin(
            tauri_plugin_single_instance::init(|app, _args, _cwd| {
                // 第二次启动时聚焦已有主窗口
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }),
        )
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            app.manage(commands::BackendProcess::default());
            #[cfg(feature = "system-audio")]
            app.manage(commands::sysaudio::SystemAudioHandle::default());
            setup_tray(app.handle())?;
            setup_overlay_window(app.handle())?;
            info!("AI Interpreter Tauri setup complete");
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_platform,
            commands::start_backend,
            commands::stop_backend,
            commands::get_backend_status,
            commands::read_desktop_settings,
            commands::save_desktop_settings,
            commands::set_overlay_visible,
            commands::get_overlay_state,
            commands::start_system_audio,
            commands::stop_system_audio,
            commands::get_system_audio_state,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

/// 创建系统托盘：点击恢复主窗口，菜单提供显示/退出。
fn setup_tray<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<()> {
    let show = MenuItem::with_id(app, "show", "显示主窗口", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show, &quit])?;

    let mut builder = TrayIconBuilder::with_id("ai-interpreter-tray")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "show" => {
                show_main_window(app);
            }
            "quit" => {
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                show_main_window(tray.app_handle());
            }
        });

    if let Some(icon) = app.default_window_icon() {
        builder = builder.icon(icon.clone());
    }

    builder.build(app)?;
    Ok(())
}

/// 创建透明悬浮字幕窗（默认隐藏）。
fn setup_overlay_window<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<()> {
    let window = tauri::WebviewWindowBuilder::new(
        app,
        "overlay",
        tauri::WebviewUrl::App("index.html?surface=overlay".into()),
    )
    .title("AI Interpreter Subtitles")
    .inner_size(920.0, 220.0)
    .min_inner_size(360.0, 80.0)
    .decorations(false)
    .transparent(true)
    .always_on_top(true)
    .skip_taskbar(true)
    .resizable(true)
    .visible(false)
    .build()?;

    // 悬浮窗贴底居中
    let _ = window.set_position(tauri::PhysicalPosition::new(80, 80));
    Ok(())
}

/// 显示并聚焦主窗口。
pub fn show_main_window<R: Runtime>(app: &AppHandle<R>) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}
