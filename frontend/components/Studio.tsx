"use client";

import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import { downloadStem, type Job } from "@/lib/api";
import { Mixer, peaks as computePeaks, type TrackState } from "@/lib/audio";
import { useTransportKeys } from "@/lib/useTransportKeys";

import { ChordLane } from "./ChordLane";
import { PracticeModes } from "./PracticeModes";
import { TrackStrip } from "./TrackStrip";
import { TrackWaveform } from "./TrackWaveform";
import { Transport } from "./Transport";
import { ZoomControl } from "./ZoomControl";
import styles from "./studio.module.css";

/**
 * Muestras por pista. El lienzo se estira con el zoom, así que hace falta
 * resolución de sobra para que a 32× no aparezcan escalones. Se calculan una
 * sola vez al cargar; TrackWaveform está memoizado para no rehacer el trazo
 * en cada frame del playhead.
 */
const WAVEFORM_BLOCKS = 8000;

/** Arranca ampliado: la lectura fina del compás es el caso normal de uso. */
const DEFAULT_ZOOM = 8;

/** Orden fijo de arriba abajo; los stems opcionales van al final. */
const ORDER = ["vocals", "bass", "drums", "other", "guitar", "piano"];

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

  // Sigue al playhead cuando se sale de la vista. No se limita a la
  // reproducción: en pausa `time` solo cambia por un salto explícito (clic o
  // flechas), así que no pelea con el scroll manual.
  useEffect(() => {
    const scroller = scrollerRef.current;
    if (!scroller || duration <= 0) return;

    const x = (time / duration) * scroller.scrollWidth;
    const visible = scroller.clientWidth;
    if (x < scroller.scrollLeft || x > scroller.scrollLeft + visible - 40) {
      scroller.scrollLeft = x - visible / 2;
    }
  }, [time, duration]);

  const currentChord = useMemo(() => {
    return job.chords.find((c) => time >= c.start && time < c.end)?.chord ?? null;
  }, [job.chords, time]);

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
  });

  function seekFromClick(event: React.MouseEvent<HTMLDivElement>) {
    const canvas = event.currentTarget.getBoundingClientRect();
    const ratio = (event.clientX - canvas.left) / canvas.width;
    withMixer((m) => m.seek(ratio * duration));
  }

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
        <ZoomControl zoom={zoom} onZoom={setZoom} />
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
              chords={job.chords}
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
