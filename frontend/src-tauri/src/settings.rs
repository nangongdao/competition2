//! 本地设置读写。
//!
//! 与 Electron 的 config/desktop-settings.local.json 对齐：
//! - 只暴露密钥是否存在（不把明文 key 送回前端）
//! - 前端提交的明文 key 只在保存时使用，快照中不包含
//! - 文件以 0600 权限写入（Unix）

use std::fs;
use std::path::PathBuf;

use serde_json::{json, Value};

/// 设置文件路径：仓库根目录下 config/desktop-settings.local.json
fn settings_path() -> PathBuf {
    // 开发模式 cwd 为 frontend；上溯两级到仓库根
    let manifest_dir = std::env::var("CARGO_MANIFEST_DIR").unwrap_or_default();
    let base = if manifest_dir.is_empty() {
        std::env::current_dir().unwrap_or_default()
    } else {
        PathBuf::from(manifest_dir)
    };
    base.parent()
        .and_then(|p| p.parent())
        .unwrap_or(&base)
        .join("config")
        .join("desktop-settings.local.json")
}

/// 读取设置快照（不含明文密钥）。
pub fn read_settings_snapshot() -> Result<Value, String> {
    let path = settings_path();
    let raw = fs::read_to_string(&path).unwrap_or_else(|_| "{}".to_string());
    let parsed: Value = serde_json::from_str(&raw).unwrap_or(Value::Object(Default::default()));

    let translation = parsed.get("translation").cloned().unwrap_or(json!({}));
    let asr = parsed.get("asr").cloned().unwrap_or(json!({}));
    let runtime = parsed.get("runtime").cloned().unwrap_or(json!({}));
    let subtitle_style = parsed.get("subtitleStyle").cloned().unwrap_or(json!({}));

    Ok(json!({
        "available": true,
        "configPath": path.to_string_lossy().to_string(),
        "uiLanguage": parsed.get("uiLanguage").and_then(Value::as_str).unwrap_or("zh-CN"),
        "translation": {
            "engine": translation.get("engine").and_then(Value::as_str).unwrap_or("openai"),
            "model": translation.get("model").and_then(Value::as_str).unwrap_or("gpt-4o-mini"),
            "openaiBaseUrl": translation.get("openaiBaseUrl").and_then(Value::as_str).unwrap_or("https://api.openai.com/v1"),
            "hasOpenaiApiKey": has_key(translation.get("openaiApiKey")),
            "hasAnthropicApiKey": has_key(translation.get("anthropicApiKey")),
        },
        "asr": {
            "model": asr.get("model").and_then(Value::as_str).unwrap_or("whisper-1"),
            "openaiBaseUrl": asr.get("openaiBaseUrl").and_then(Value::as_str).unwrap_or("https://api.openai.com/v1"),
            "hasOpenaiApiKey": has_key(asr.get("openaiApiKey")),
        },
        "runtime": {
            "asrProfile": runtime.get("asrProfile").and_then(Value::as_str).unwrap_or("remote"),
            "sourceLanguage": runtime.get("sourceLanguage").and_then(Value::as_str).unwrap_or("en"),
            "targetLanguage": runtime.get("targetLanguage").and_then(Value::as_str).unwrap_or("zh-CN"),
        },
        "subtitleStyle": {
            "fontSize": subtitle_style.get("fontSize").and_then(Value::as_i64).unwrap_or(22),
            "fontColor": subtitle_style.get("fontColor").and_then(Value::as_str).unwrap_or("#ffffff"),
            "backgroundColor": subtitle_style.get("backgroundColor").and_then(Value::as_str).unwrap_or("#0a0e16"),
            "backgroundOpacity": subtitle_style.get("backgroundOpacity").and_then(Value::as_f64).unwrap_or(0.78),
            "position": subtitle_style.get("position").and_then(Value::as_str).unwrap_or("bottom"),
        }
    }))
}

/// 应用设置更新：合并到本地 JSON 文件（密钥仅在保存时写入）。
pub fn write_settings_update(update: Value) -> Result<Value, String> {
    let path = settings_path();
    if let Some(dir) = path.parent() {
        fs::create_dir_all(dir).map_err(|e| e.to_string())?;
    }

    let mut current: Value = fs::read_to_string(&path)
        .ok()
        .and_then(|raw| serde_json::from_str(&raw).ok())
        .unwrap_or(Value::Object(Default::default()));

    merge_update(&mut current, &update);

    let serialized = serde_json::to_string_pretty(&current).map_err(|e| e.to_string())?;
    fs::write(&path, serialized.as_bytes()).map_err(|e| e.to_string())?;

    // Unix 下收紧权限
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = fs::set_permissions(&path, fs::Permissions::from_mode(0o600));
    }

    read_settings_snapshot()
}

fn has_key(value: Option<&Value>) -> bool {
    match value {
        Some(Value::String(s)) => !s.trim().is_empty(),
        _ => false,
    }
}

fn merge_update(current: &mut Value, update: &Value) {
    let Some(update_obj) = update.as_object() else {
        return;
    };

    if !current.is_object() {
        *current = Value::Object(Default::default());
    }
    let current_obj = current.as_object_mut().expect("object ensured");

    for (key, value) in update_obj {
        if let Some(nested) = value.as_object() {
            let entry = current_obj
                .entry(key.clone())
                .or_insert_with(|| Value::Object(Default::default()));
            merge_update(entry, &Value::Object(nested.clone()));
        } else {
            current_obj.insert(key.clone(), value.clone());
        }
    }
}
