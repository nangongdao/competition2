// 静音丢弃：会议中静音占比通常达 30-40%，完全丢弃可显著降低带宽与后端 ASR 调用。
// RMS 低于该阈值视为静音。
const SILENCE_RMS_THRESHOLD = 0.008
// 连续静音每隔该帧数发送一个心跳静音帧，让后端仍能感知静音边界
//（AdaptiveSegmenter 依赖尾部静音触发句子切分），其余静音帧丢弃。
const SILENCE_HEARTBEAT_FRAMES = 60

function computeRms(samples) {
  let sumSquares = 0
  for (let i = 0; i < samples.length; i += 1) {
    sumSquares += samples[i] * samples[i]
  }
  return Math.sqrt(sumSquares / samples.length)
}

class AudioCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this._silentFrames = 0
    this._droppedFrames = 0
  }

  process(inputs, outputs) {
    const input = inputs[0]
    const output = outputs[0]

    if (output) {
      for (const channel of output) {
        channel.fill(0)
      }
    }

    if (!input || input.length === 0) {
      return true
    }

    const sourceChannel = input[0]
    if (!sourceChannel || sourceChannel.length === 0) {
      return true
    }

    const samples = new Float32Array(sourceChannel.length)
    samples.set(sourceChannel)

    // 静音帧丢弃：连续静音只发心跳，节省带宽与后端算力
    const rms = computeRms(samples)
    if (rms < SILENCE_RMS_THRESHOLD) {
      this._silentFrames += 1
      this._droppedFrames += 1
      if (this._silentFrames % SILENCE_HEARTBEAT_FRAMES !== 0) {
        return true
      }
    } else {
      this._silentFrames = 0
    }

    this.port.postMessage(
      {
        type: 'audio-chunk',
        samples,
        rms,
        silent: rms < SILENCE_RMS_THRESHOLD,
      },
      [samples.buffer],
    )

    return true
  }
}

registerProcessor('audio-capture-processor', AudioCaptureProcessor)
