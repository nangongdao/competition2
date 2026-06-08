class AudioCaptureProcessor extends AudioWorkletProcessor {
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

    this.port.postMessage(
      {
        type: 'audio-chunk',
        samples,
      },
      [samples.buffer],
    )

    return true
  }
}

registerProcessor('audio-capture-processor', AudioCaptureProcessor)
