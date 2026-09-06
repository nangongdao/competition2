//! 系统音频 loopback 采集（实验特性）。
//!
//! 通过 cpal 捕获系统输出（loopback 设备），以二进制帧推送给前端。
//! 该特性依赖本机安装 loopback 驱动（Windows WASAPI / macOS BlackHole /
//! Linux PulseAudio monitor），默认不启用，需 `--features system-audio` 编译。

#![cfg(feature = "system-audio")]

use tauri::{AppHandle, Emitter};

use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};

/// 系统音频采集器：持有 cpal 输入流与设备元数据。
pub struct SystemAudioCapture {
    stream: Option<cpal::Stream>,
    device_name: Option<String>,
    sample_rate: u32,
    channels: u16,
}

// SAFETY: cpal 的 Stream 在 ALSA/部分后端含 raw pointer，非自动 Send/Sync。
// 我们保证所有 start/stop 调用都经由 commands.rs 的 Mutex 串行执行，
// stream 从不跨线程移动，因此手动标记 Send+Sync 是安全的（社区标准做法）。
unsafe impl Send for SystemAudioCapture {}
unsafe impl Sync for SystemAudioCapture {}

impl SystemAudioCapture {
    pub fn new() -> Self {
        Self {
            stream: None,
            device_name: None,
            sample_rate: 0,
            channels: 0,
        }
    }

    /// 开始采集系统输出音频并推送给前端 `audio:data` 事件。
    pub fn start(&mut self, app: AppHandle) -> Result<(), String> {
        if self.stream.is_some() {
            return Ok(());
        }

        let host = cpal::default_host();
        let device = host
            .output_devices()
            .map_err(|e| e.to_string())?
            .find(|device| {
                device
                    .name()
                    .map(|name| {
                        name.contains("Loopback")
                            || name.contains("Stereo Mix")
                            || name.contains("BlackHole")
                            || name.contains("VB-Audio")
                            || name.contains("Monitor")
                    })
                    .unwrap_or(false)
            })
            .ok_or_else(|| {
                "未找到 loopback 音频设备，请安装 BlackHole / VB-Audio Cable / PulseAudio Monitor"
                    .to_string()
            })?;

        let device_name = device.name().ok();
        let config = device.default_input_config().map_err(|e| e.to_string())?;
        let sample_rate = config.sample_rate().0;
        let channels = config.channels();

        let stream = device
            .build_input_stream(
                &config.into(),
                move |data: &[f32], _: &cpal::InputCallbackInfo| {
                    let bytes = unsafe {
                        std::slice::from_raw_parts(
                            data.as_ptr() as *const u8,
                            data.len() * std::mem::size_of::<f32>(),
                        )
                    };
                    let _ = app.emit(
                        "audio:data",
                        serde_json::json!({
                            "data": base64_encode(bytes),
                            "sampleRate": sample_rate,
                            "channels": channels,
                        }),
                    );
                },
                |err| eprintln!("Audio capture error: {}", err),
                None,
            )
            .map_err(|e| e.to_string())?;

        stream.play().map_err(|e| e.to_string())?;
        self.stream = Some(stream);
        self.device_name = device_name;
        self.sample_rate = sample_rate;
        self.channels = channels;
        Ok(())
    }

    /// 停止采集并释放设备。
    pub fn stop(&mut self) {
        if let Some(stream) = self.stream.take() {
            let _ = stream.pause();
            drop(stream);
        }
    }
}

fn base64_encode(bytes: &[u8]) -> String {
    const TABLE: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for chunk in bytes.chunks(3) {
        let b0 = chunk[0] as u32;
        let b1 = chunk.get(1).copied().unwrap_or(0) as u32;
        let b2 = chunk.get(2).copied().unwrap_or(0) as u32;
        let n = (b0 << 16) | (b1 << 8) | b2;
        out.push(TABLE[(n >> 18) as usize & 63] as char);
        out.push(TABLE[(n >> 12) as usize & 63] as char);
        out.push(if chunk.len() > 1 {
            TABLE[(n >> 6) as usize & 63] as char
        } else {
            '='
        });
        out.push(if chunk.len() > 2 {
            TABLE[n as usize & 63] as char
        } else {
            '='
        });
    }
    out
}

#[cfg(test)]
mod tests {
    use super::base64_encode;

    #[test]
    fn base64_encodes_standard_inputs() {
        assert_eq!(base64_encode(b""), "");
        assert_eq!(base64_encode(b"f"), "Zg==");
        assert_eq!(base64_encode(b"fo"), "Zm8=");
        assert_eq!(base64_encode(b"foo"), "Zm9v");
        assert_eq!(base64_encode(b"foob"), "Zm9vYg==");
        assert_eq!(base64_encode(b"fooba"), "Zm9vYmE=");
        assert_eq!(base64_encode(b"foobar"), "Zm9vYmFy");
    }

    #[test]
    fn base64_matches_reference_implementation() {
        // 与 Python base64 标准库对比的已知向量
        let data: Vec<u8> = (0u8..=255).collect();
        let encoded = base64_encode(&data);
        assert!(encoded.len() == 344);
        assert!(encoded.starts_with("AAECAwQFBgcICQoL"));
        assert!(encoded.ends_with("8PHy8/T19vf4+fr7/P3+/w=="));
    }
}
