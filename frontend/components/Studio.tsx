"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import { downloadStem, type Job } from "@/lib/api";
import { Mixer, peaks as computePeaks, type TrackState } from "@/lib/audio";
import { simplifyChords, type ChordDetail } from "@/lib/chords";
import { useTransportKeys } from "@/lib/useTransportKeys";

import { ChordDetailControl } from "./ChordDetailControl";
import { ChordLane } from "./ChordLane";
import { PracticeModes } from "./PracticeModes";
import { TrackStrip } from "./TrackStrip";
import { TrackWaveform } from "./TrackWaveform";
import { Transport } from "./Transport";
import { ZoomControl } from "./ZoomControl";
import styles from "./studio.module.css";

/**
 * Muestras por pista. El lienzo se estira con el zoom, así que hace falta
 * resolución de sobra para que en los zooms altos no aparezcan escalones:
 * a 32× esto deja ~750 segmentos por pantalla, cerca de uno cada dos píxeles.
 * Más allá de 64× el trazo vuelve a engordar, pero ahí ya se está mirando un
 * puñado de segundos. Se calculan una sola vez al cargar; TrackWaveform está
 * memoizado para no rehacer el trazo en cada frame del playhead.
 */
const WAVEFORM_BLOCKS = 24000;

/** Arranca ampliado: la lectura fina del compás es el caso normal de uso. */
const DEFAULT_ZOOM = 32;

/** Preferencia del usuario, no dato del trabajo: sobrevive a cambiar de canción. */
const DETAIL_KEY = "mewsplit.chordDetail";

/** Orden fijo de arriba abajo; los stems opcionales van al final. */
const ORDER = ["vocals", "bass", "drums", "guitar", "other", "piano"];

interface Props {
  job: Job;
}

export function Studio({ job }: Props) {
  const mixerRef = useRef<Mixer | null>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [tracks, setTracks] = useState<TrackState[]>([]);
  const [waveforms, setWaveforms] = useState<Record<string, Float32Array>>({});
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [zoom, setZoom] = useState(DEFAULT_ZOOM);
  const [detail, setDetail] = useState<ChordDetail>(readDetail);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const mixer = new Mixer();
    mixerRef.current = mixer;
    let alive = true;

    (async () => {
      try {
        const names = Object.keys(job.stems)
          .filter((name) => name !== "instrumental")
          .sort((a, b) => orderOf(a) - orderOf(b));

        const inputs = await Promise.all(
          names.map(async (name) => ({ name, data: await downloadStem(job.id, name) })),
        );
        if (!alive) return;

        await mixer.load(inputs);
        if (!alive) return;

        setTracks(mixer.state());
        setDuration(mixer.duration);
        setWaveforms(buildWaveforms(mixer, names));
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      }
    })();

    // rAF solo pinta: la posición siempre sale del reloj del contexto de audio.
    const unsubscribe = mixer.subscribe((t, isPlaying) => {
      setTime(t);
      setPlaying(isPlaying);
    });

    return () => {
      alive = false;
      unsubscribe();
      void mixer.close();
      mixerRef.current = null;
    };
  }, [job.id, job.stems]);

  
  useEffect(() => {
    const scroller = scrollerRef.current;
    if (!scroller || duration <= 0) return;

    const x = (time / duration) * scroller.scrollWidth;
    const visible = scroller.clientWidth;
    const ahead = visible * 0.85;
    if (x < scroller.scrollLeft || x > scroller.scrollLeft + ahead) {
      scroller.scrollLeft = x - visible * 0.25;
    }
  }, [time, duration]);

  const chords = useMemo(
    () => (detail === "simple" ? simplifyChords(job.chords) : job.chords),
    [job.chords, detail],
  );

  const currentChord = useMemo(() => {
    return chords.find((c) => time >= c.start && time < c.end)?.chord ?? null;
  }, [chords, time]);

  function changeDetail(next: ChordDetail) {
    setDetail(next);
    try {
      localStorage.setItem(DETAIL_KEY, next);
    } catch {
      // Sin almacenamiento (ventana privada, datos bloqueados) solo se pierde el recuerdo.
    }
  }

  const names = useMemo(() => tracks.map((t) => t.name), [tracks]);
  const soloed = useMemo(() => tracks.filter((t) => t.soloed).map((t) => t.name), [tracks]);

  function withMixer(action: (mixer: Mixer) => void) {
    const mixer = mixerRef.current;
    if (!mixer) return;
    action(mixer);
    setTracks(mixer.state());
  }

  useTransportKeys({
    onToggle: () => withMixer((m) => void m.toggle()),
    onNudge: (seconds) => withMixer((m) => m.seek(m.time + seconds)),
    onJump: (fraction) => withMixer((m) => m.seek(fraction * duration)),
  });

  function seekFromClick(event: React.MouseEvent<HTMLDivElement>) {
    const canvas = event.currentTarget.getBoundingClientRect();
    const ratio = (event.clientX - canvas.left) / canvas.width;
    withMixer((m) => m.seek(ratio * duration));
  }

  const [saving, setSaving] = useState(false);

  const saveMix = useCallback(async () => {
    const mixer = mixerRef.current;
    if (!mixer || saving) return;

    setSaving(true);
    try {
      const blob = await mixer.renderMix();
      if (!blob) return;

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${saveName(job, soloed)}.wav`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setSaving(false);
    }
  }, [saving, job, soloed]);

  const saveLabel = saving
    ? "rendering…"
    : soloed.length > 0
      ? `save mix · ${soloed.join(" + ")}`
      : "save mix";

  if (error) {
    return <p className="label">no se pudieron cargar los stems: {error}</p>;
  }

  const canvas = {
    "--zoom": zoom,
    "--progress": duration > 0 ? time / duration : 0,
  } as CSSProperties;

  return (
    <div className={styles.studio}>
      <div className={styles.toolbar}>
        <PracticeModes
          names={names}
          active={soloed}
          onMode={(picked) =>
            withMixer((m) => (picked.length === 0 ? m.reset() : m.isolate(picked)))
          }
        />
        <div className={styles.toolbarRight}>
          <ChordDetailControl detail={detail} onDetail={changeDetail} />
          <button
            type="button"
            className={`label ${styles.saveMix}`}
            onClick={saveMix}
            disabled={saving || tracks.length === 0}
          >
            {saveLabel}
          </button>
          <ZoomControl zoom={zoom} onZoom={setZoom} />
        </div>
      </div>

      <div className={styles.board}>
        {/* Columna fija: el scroll horizontal no debe llevarse los controles. */}
        <div className={styles.mixer}>
          <div className={styles.chordSpacer} />
          {tracks.map((track) => (
            <TrackStrip
              key={track.name}
              track={track}
              onVolume={(value) => withMixer((m) => m.setVolume(track.name, value))}
              onMute={() => withMixer((m) => m.mute(track.name))}
              onSolo={() => withMixer((m) => m.solo(track.name))}
            />
          ))}
        </div>

        {/* Un solo contenedor desplazable: acordes y ondas van sincronizados
            porque comparten scroll, no porque nadie los sincronice. */}
        <div className={styles.scroller} ref={scrollerRef}>
          <div className={styles.canvas} style={canvas} onClick={seekFromClick}>
            <ChordLane
              chords={chords}
              duration={duration}
              time={time}
              onSeek={(second) => withMixer((m) => m.seek(second))}
            />

            {tracks.map((track) => (
              <TrackWaveform
                key={track.name}
                peaks={waveforms[track.name] ?? null}
                muted={!track.audible}
              />
            ))}

            <div className={styles.playhead} />
          </div>
        </div>
      </div>

      <Transport
        playing={playing}
        time={time}
        duration={duration}
        currentChord={currentChord}
        onToggle={() => withMixer((m) => void m.toggle())}
      />
    </div>
  );
}

function readDetail(): ChordDetail {
  try {
    const stored = localStorage.getItem(DETAIL_KEY);
    // "triads" es el nombre anterior de "simple": quien ya lo eligió no lo pierde.
    return stored === "simple" || stored === "triads" ? "simple" : "full";
  } catch {
    return "full";
  }
}

function orderOf(name: string): number {
  const index = ORDER.indexOf(name);
  return index === -1 ? ORDER.length : index;
}

function buildWaveforms(mixer: Mixer, names: string[]): Record<string, Float32Array> {
  const output: Record<string, Float32Array> = {};
  for (const name of names) {
    const buffer = mixer.bufferOf(name);
    // La duración total, no la de la pista: todas comparten eje.
    if (buffer) output[name] = computePeaks(buffer, WAVEFORM_BLOCKS, mixer.duration);
  }
  return output;
}

/** Nombre del archivo descargado: "título - stems seleccionados". */
function saveName(job: Job, soloed: string[]): string {
  const base = job.filename?.replace(/\.[^.]+$/, "") ?? job.id;
  if (soloed.length === 0) return `${base} - full mix`;
  return `${base} - ${soloed.join("+")}`;
}
