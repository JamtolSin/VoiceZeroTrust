/* Capture on the audio thread, not the page rendering thread. No history buffer. */
class Pcm16Sender extends AudioWorkletProcessor {
  constructor() {
    super();
    this.frame = new ArrayBuffer(640);
    this.view = new DataView(this.frame);
    this.offset = 0;
  }
  process(inputs) {
    const samples = inputs[0]?.[0];
    if (samples) {
      for (const sample of samples) {
        this.view.setInt16(this.offset, Math.round(Math.max(-1, Math.min(1, sample)) * 32767), true);
        this.offset += 2;
        if (this.offset === 640) {
          this.port.postMessage(this.frame, [this.frame]);
          this.frame = new ArrayBuffer(640);
          this.view = new DataView(this.frame);
          this.offset = 0;
        }
      }
    }
    // Outputs stay silent: local microphone is transmitted, never locally played.
    return true;
  }
}
registerProcessor('pcm16-sender', Pcm16Sender);
