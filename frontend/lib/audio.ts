/**
 * audio.ts — mezclador multipista sobre Web Audio API.
 *
 * El problema central: cuatro fuentes que deben sonar en fase, un playhead
 * que las sigue y bucles que saltan sin desalinearlas.
 *
 * Cómo se resuelve:
 *
 * 1. **Un solo reloj.** `AudioContext.currentTime` es la única fuente de
 *    verdad. `requestAnimationFrame` solo pinta; nunca decide la posición.
 *    Derivar el tiempo de rAF acumula deriva y desincroniza el playhead.
 *
 * 2. **Un solo `when`.** Todas las fuentes se programan con el mismo instante
 *    absoluto, calculado una vez. Arrancarlas en un bucle con `start(0)` las
 *    separa por el tiempo que tarde el propio bucle.
 *
 * 3. **El bucle lo hace el hilo de audio.** `loop`/`loopStart`/`loopEnd` sobre
 *    cada fuente salta con precisión de muestra. Detectar el final desde rAF
 *    y reprogramar introduce un salto audible y distinto en cada pista.
 *
 * Cada pista se reconstruye entera al buscar o al cambiar el bucle: un
 * `AudioBufferSourceNode` es de un solo uso.
 *
 * 4. **La velocidad no rompe ninguna de las tres.** Todas las fuentes cambian
 *    su `playbackRate` en el mismo instante del reloj, así que siguen en fase,
 *    y el tono se corrige DESPUÉS de mezclar, en un solo nodo (SoundTouch):
 *    corregirlo por pista exigiría un procesador por stem y podría desfasarlas.
 */

// Solo el tipo: la librería define su nodo extendiendo AudioWorkletNode al
// importarse, y eso revienta al prerenderizar la página en Node.
import type { SoundTouchNode } from "@soundtouchjs/audio-worklet";

/** Margen para programar el arranque sin llegar tarde al hilo de audio. */
const LOOKAHEAD = 0.02;

/** Rampa corta en los cambios de ganancia; sin ella se oye un clic. */
const RAMP = 0.015;

/**
 * Límites de velocidad. Fuera de este rango SoundTouch se oye cada vez peor
 * (y por encima de 1.5 empieza a quedarse sin muestras en el hilo de audio).
 */
export const SPEED_MIN = 0.5;
export const SPEED_MAX = 1.5;

/** Lo sirve la interfaz; lo copia scripts/copy-worklet.mjs desde el paquete. */
const PROCESSOR_URL = "/soundtouch-processor.js";

export interface TrackInput {
  name: string;
  data: ArrayBuffer;
}

export interface TrackState {
  name: string;
  volume: number;
  muted: boolean;
  soloed: boolean;
  audible: boolean;
}

export interface Loop {
  start: number;
  end: number;
}

interface Track {
  name: string;
  buffer: AudioBuffer;
  gain: GainNode;
  volume: number;
  muted: boolean;
  soloed: boolean;
}

export function toDecibels(volume: number): number {
  return volume <= 0.0001 ? -Infinity : 20 * Math.log10(volume);
}

export function fromDecibels(db: number): number {
  return db === -Infinity ? 0 : Math.pow(10, db / 20);
}

export class Mixer {
  private ctx: AudioContext;
  private master: GainNode;
  private tracks = new Map<string, Track>();
  private sources: AudioBufferSourceNode[] = [];

  private isPlaying = false;
  private contextStart = 0;
  private position = 0;
  private currentLoop: Loop | null = null;
  private totalDuration = 0;
  private rate = 1;
  /** Corrector de tono; null hasta que se registra (o si el navegador no puede). */
  private stretch: SoundTouchNode | null = null;

  constructor(ctx?: AudioContext) {
    this.ctx = ctx ?? new AudioContext();
    this.master = this.ctx.createGain();
    this.master.connect(this.ctx.destination);
  }

  get duration(): number {
    return this.totalDuration;
  }

  get playing(): boolean {
    return this.isPlaying;
  }

  get loop(): Loop | null {
    return this.currentLoop;
  }

  /** Velocidad de reproducción: 1 es la original. */
  get speed(): number {
    return this.rate;
  }

  /** Si al cambiar la velocidad se mantiene el tono (hay corrector cargado). */
  get keepsPitch(): boolean {
    return this.stretch !== null;
  }

  /**
   * Posición actual en segundos de la canción, derivada del reloj del
   * contexto. Es la que debe pintar el playhead.
   */
  get time(): number {
    return this.timeAt(this.ctx.currentTime);
  }

  /** Posición de la canción en un instante dado del reloj del contexto. */
  private timeAt(contextTime: number): number {
    if (!this.isPlaying) return this.position;

    const elapsed = contextTime - this.contextStart;
    // Antes del instante programado el audio aún no ha empezado a sonar.
    if (elapsed <= 0) return this.position;

    // A velocidad 0.5, cada segundo de reloj avanza medio segundo de canción.
    let t = this.position + elapsed * this.rate;

    if (this.currentLoop) {
      const { start, end } = this.currentLoop;
      const span = end - start;
      if (span > 0 && t >= end) {
        t = start + ((t - start) % span);
      }
    }

    return Math.min(t, this.totalDuration);
  }

  async load(inputs: TrackInput[]): Promise<void> {
    this.stop();
    this.tracks.clear();

    const decoded = await Promise.all(
      inputs.map(async (input) => ({
        name: input.name,
        // decodeAudioData consume el ArrayBuffer: se copia por si el llamador lo reusa.
        buffer: await this.ctx.decodeAudioData(input.data.slice(0)),
      })),
    );

    for (const { name, buffer } of decoded) {
      const gain = this.ctx.createGain();
      gain.connect(this.master);
      this.tracks.set(name, { name, buffer, gain, volume: 1, muted: false, soloed: false });
    }

    // Los stems salen del mismo audio, pero pueden diferir en unos frames.
    this.totalDuration = Math.max(0, ...decoded.map((d) => d.buffer.duration));
    this.position = 0;
    this.applyGains(0);
  }

  get names(): string[] {
    return [...this.tracks.keys()];
  }

  /** Buffer decodificado de una pista, para dibujar su forma de onda. */
  bufferOf(name: string): AudioBuffer | null {
    return this.tracks.get(name)?.buffer ?? null;
  }

  state(): TrackState[] {
    const soloActive = this.hasSolo();
    return [...this.tracks.values()].map((track) => ({
      name: track.name,
      volume: track.volume,
      muted: track.muted,
      soloed: track.soloed,
      audible: !track.muted && (!soloActive || track.soloed),
    }));
  }

  async play(): Promise<void> {
    if (this.isPlaying || this.tracks.size === 0) return;

    // Los navegadores arrancan el contexto suspendido hasta un gesto del usuario.
    if (this.ctx.state === "suspended") await this.ctx.resume();

    if (this.position >= this.totalDuration) this.position = 0;
    this.schedule(this.position);
  }

  pause(): void {
    if (!this.isPlaying) return;
    const t = this.time;
    this.stopSources();
    this.position = t;
    this.isPlaying = false;
  }

  toggle(): Promise<void> | void {
    return this.isPlaying ? this.pause() : this.play();
  }

  stop(): void {
    this.stopSources();
    this.isPlaying = false;
    this.position = 0;
  }

  /** Salta a un instante. Si suena, se reprograma sin perder la fase entre pistas. */
  seek(seconds: number): void {
    const target = Math.max(0, Math.min(seconds, this.totalDuration));
    if (this.isPlaying) {
      this.stopSources();
      this.schedule(target);
    } else {
      this.position = target;
    }
  }

  /** `null` desactiva el bucle. Reprograma las fuentes si están sonando. */
  setLoop(loop: Loop | null): void {
    if (loop && loop.end - loop.start <= 0) {
      throw new RangeError("El bucle necesita duración positiva");
    }
    this.currentLoop = loop;

    if (this.isPlaying) {
      const t = this.time;
      this.stopSources();
      this.schedule(loop ? Math.max(t, loop.start) : t);
    }
  }

  /**
   * Carga el corrector de tono. Sin él, cambiar la velocidad también cambia
   * el tono (como un tocadiscos). Devuelve si quedó disponible.
   */
  async enablePitchCorrection(): Promise<boolean> {
    if (this.stretch) return true;
    try {
      const { SoundTouchNode } = await import("@soundtouchjs/audio-worklet");
      await SoundTouchNode.register(this.ctx, PROCESSOR_URL);
      this.stretch = new SoundTouchNode({ context: this.ctx });
      this.stretch.connect(this.ctx.destination);
      this.route();
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Cambia la velocidad sin cortar el sonido: todas las fuentes cambian su
   * `playbackRate` en el mismo instante del reloj, así que siguen en fase.
   */
  setSpeed(value: number): void {
    const rate = Math.max(SPEED_MIN, Math.min(value, SPEED_MAX));
    if (rate === this.rate) return;

    const at = this.ctx.currentTime + LOOKAHEAD;
    if (this.isPlaying) {
      // La posición se reancla en el instante del cambio: lo sonado hasta ahí
      // fue a la velocidad vieja, lo que viene va a la nueva.
      this.position = this.timeAt(at);
      this.contextStart = at;
      for (const source of this.sources) source.playbackRate.setValueAtTime(rate, at);
    }
    this.rate = rate;
    this.stretch?.playbackRate.setValueAtTime(rate, at);
    this.route();
  }

  /**
   * A velocidad 1 la mezcla va directa a la salida, como siempre; SoundTouch
   * solo entra cuando hace falta corregir el tono. Así a velocidad normal no
   * hay ni el retardo ni el procesado del corrector.
   */
  private route(): void {
    this.master.disconnect();
    this.master.connect(this.stretch && this.rate !== 1 ? this.stretch : this.ctx.destination);
  }

  setVolume(name: string, value: number): void {
    const track = this.tracks.get(name);
    if (!track) return;
    track.volume = Math.max(0, Math.min(value, 1));
    this.applyGains();
  }

  mute(name: string, muted?: boolean): void {
    const track = this.tracks.get(name);
    if (!track) return;
    track.muted = muted ?? !track.muted;
    this.applyGains();
  }

  solo(name: string, soloed?: boolean): void {
    const track = this.tracks.get(name);
    if (!track) return;
    track.soloed = soloed ?? !track.soloed;
    this.applyGains();
  }

  /** Deja sonando solo las pistas indicadas. Base de los modos de práctica. */
  isolate(names: string[]): void {
    const wanted = new Set(names);
    for (const track of this.tracks.values()) {
      track.soloed = wanted.has(track.name);
      track.muted = false;
    }
    this.applyGains();
  }

  reset(): void {
    for (const track of this.tracks.values()) {
      track.volume = 1;
      track.muted = false;
      track.soloed = false;
    }
    this.applyGains();
  }

  setMasterVolume(value: number): void {
    this.ramp(this.master, Math.max(0, Math.min(value, 1)));
  }

  /**
   * Llama a `callback` una vez por frame mientras suene. Devuelve la función
   * para darse de baja. rAF solo pinta: la posición sale del reloj del contexto.
   */
  subscribe(callback: (time: number, playing: boolean) => void): () => void {
    let active = true;
    const tick = () => {
      if (!active) return;
      callback(this.time, this.isPlaying);
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
    return () => {
      active = false;
    };
  }

  async close(): Promise<void> {
    this.stop();
    this.tracks.clear();
    await this.ctx.close();
  }

  private hasSolo(): boolean {
    for (const track of this.tracks.values()) {
      if (track.soloed) return true;
    }
    return false;
  }

  private applyGains(ramp = RAMP): void {
    const soloActive = this.hasSolo();
    for (const track of this.tracks.values()) {
      const audible = !track.muted && (!soloActive || track.soloed);
      this.ramp(track.gain, audible ? track.volume : 0, ramp);
    }
  }

  private ramp(node: GainNode, value: number, duration = RAMP): void {
    const now = this.ctx.currentTime;
    node.gain.cancelScheduledValues(now);
    node.gain.setValueAtTime(node.gain.value, now);
    node.gain.linearRampToValueAtTime(value, now + duration);
  }

  /**
   * Programa todas las fuentes con el MISMO instante absoluto. Ese `when`
   * compartido es lo que las mantiene en fase.
   */
  private schedule(from: number): void {
    const when = this.ctx.currentTime + LOOKAHEAD;

    for (const track of this.tracks.values()) {
      const source = this.ctx.createBufferSource();
      source.buffer = track.buffer;
      source.playbackRate.value = this.rate;
      source.connect(track.gain);

      if (this.currentLoop) {
        source.loop = true;
        source.loopStart = this.currentLoop.start;
        source.loopEnd = Math.min(this.currentLoop.end, track.buffer.duration);
      }

      source.start(when, from);
      this.sources.push(source);
    }

    // Una sola fuente avisa del final; todas terminan en el mismo instante.
    const last = this.sources[this.sources.length - 1];
    if (last && !this.currentLoop) {
      last.onended = () => {
        if (!this.isPlaying) return;
        this.stopSources();
        this.isPlaying = false;
        this.position = this.totalDuration;
      };
    }

    this.contextStart = when;
    this.position = from;
    this.isPlaying = true;
  }

  private stopSources(): void {
    for (const source of this.sources) {
      source.onended = null;
      try {
        source.stop();
      } catch {
        // Ya había terminado por su cuenta.
      }
      source.disconnect();
    }
    this.sources = [];
  }

  /**
   * Renderiza offline la mezcla actual (respetando solo/mute/volume) a un
   * Blob WAV de 16 bits. Devuelve `null` si no hay pistas cargadas.
   *
   * Siempre a velocidad original: la velocidad es una ayuda para practicar,
   * no parte de la mezcla.
   *
   * No toca el contexto de reproducción: usa un OfflineAudioContext aparte.
   */
  async renderMix(): Promise<Blob | null> {
    if (this.tracks.size === 0) return null;

    const soloActive = this.hasSolo();
    const audible = [...this.tracks.values()].filter(
      (t) => !t.muted && (!soloActive || t.soloed),
    );

    // Si nada está audible, mezcla todo (equivale a "nada seleccionado").
    const toRender = audible.length > 0 ? audible : [...this.tracks.values()];

    const sampleRate = toRender[0].buffer.sampleRate;
    const length = Math.round(this.totalDuration * sampleRate);
    const channels = 2;
    const offline = new OfflineAudioContext(channels, length, sampleRate);

    for (const track of toRender) {
      const source = offline.createBufferSource();
      source.buffer = track.buffer;
      const gain = offline.createGain();
      gain.gain.value = track.volume;
      source.connect(gain).connect(offline.destination);
      source.start(0);
    }

    const rendered = await offline.startRendering();
    return encodeWav(rendered);
  }
}

/**
 * Codifica un AudioBuffer a WAV PCM 16-bit little-endian.
 * Mezcla todos los canales a estéreo (o mono si solo hay uno).
 */
function encodeWav(buffer: AudioBuffer): Blob {
  const numChannels = Math.min(buffer.numberOfChannels, 2);
  const sampleRate = buffer.sampleRate;
  const length = buffer.length;
  const bytesPerSample = 2;
  const dataSize = length * numChannels * bytesPerSample;

  const headerSize = 44;
  const arrayBuffer = new ArrayBuffer(headerSize + dataSize);
  const view = new DataView(arrayBuffer);

  // RIFF header
  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeString(view, 8, "WAVE");

  // fmt chunk
  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * numChannels * bytesPerSample, true);
  view.setUint16(32, numChannels * bytesPerSample, true);
  view.setUint16(34, bytesPerSample * 8, true);

  // data chunk
  writeString(view, 36, "data");
  view.setUint32(40, dataSize, true);

  const channels: Float32Array[] = [];
  for (let ch = 0; ch < numChannels; ch++) {
    channels.push(buffer.getChannelData(ch));
  }

  let offset = headerSize;
  for (let i = 0; i < length; i++) {
    for (let ch = 0; ch < numChannels; ch++) {
      const sample = Math.max(-1, Math.min(1, channels[ch][i]));
      view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
      offset += bytesPerSample;
    }
  }

  return new Blob([arrayBuffer], { type: "audio/wav" });
}

function writeString(view: DataView, offset: number, str: string): void {
  for (let i = 0; i < str.length; i++) {
    view.setUint8(offset + i, str.charCodeAt(i));
  }
}

/**
 * Picos por bloque para dibujar la forma de onda, en el rango 0..1.
 * Comparte eje temporal con la línea de acordes: mismo número de bloques,
 * misma duración total.
 */
export function peaks(
  buffer: AudioBuffer,
  blocks: number,
  totalDuration = buffer.duration,
): Float32Array {
  const samples = buffer.getChannelData(0);
  const output = new Float32Array(blocks);
  if (totalDuration <= 0) return output;

  // Los bloques cubren la duración total de la sesión, no la de esta pista:
  // un stem unos frames más corto tiene que quedarse corto, no estirarse
  // hasta el final y desalinearse del resto del eje.
  const samplesPerBlock = (buffer.sampleRate * totalDuration) / blocks;

  for (let i = 0; i < blocks; i++) {
    const start = Math.floor(i * samplesPerBlock);
    const end = Math.min(Math.floor((i + 1) * samplesPerBlock), samples.length);
    let peak = 0;
    for (let j = start; j < end; j++) {
      const value = Math.abs(samples[j]);
      if (value > peak) peak = value;
    }
    output[i] = peak;
  }
  return output;
}
