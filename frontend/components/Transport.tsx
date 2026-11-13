"use client";

import { formatChord } from "@/lib/chords";

import { SpeedControl } from "./SpeedControl";
import styles from "./studio.module.css";

interface Props {
  ready: boolean;
  playing: boolean;
  time: number;
  duration: number;
  currentChord: string | null;
  nextChord: string | null;
  onToggle: () => void;
  onRestart: () => void;
  speed: number;
  keepsPitch: boolean;
  onSpeed: (speed: number) => void;
}

export function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) seconds = 0;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${String(minutes).padStart(2, "0")}:${rest.toFixed(1).padStart(4, "0")}`;
}

export function Transport({
  ready,
  playing,
  time,
  duration,
  currentChord,
  nextChord,
  onToggle,
  onRestart,
  speed,
  keepsPitch,
  onSpeed,
}: Props) {
  const sounding = currentChord && currentChord !== "N" ? currentChord : null;

  return (
    <div className={styles.transport}>
      <div className={styles.transportGroup}>
        <button
          type="button"
          className={`button primary ${styles.play}`}
          onClick={onToggle}
          disabled={!ready}
          title="Espacio para reproducir o pausar"
        >
          <PlayGlyph playing={playing} />
          {playing ? "Pausa" : "Reproducir"}
          <span className={styles.key}>espacio</span>
        </button>
        <button type="button" className="button" onClick={onRestart} disabled={!ready} title="Tecla 0">
          Inicio
        </button>
      </div>

      <span className={`data ${styles.clock}`}>
        {formatTime(time)} <span className={styles.clockTotal}>/ {formatTime(duration)}</span>
      </span>

      <span className={styles.chordReadout}>
        <span className="label">Acorde</span>
        <span className={`${styles.chordNow} ${sounding ? styles.chordSounding : ""}`}>
          {sounding ? formatChord(sounding) : "—"}
        </span>
        {nextChord && (
          <span className={styles.chordNext} title="El siguiente">
            → {formatChord(nextChord)}
          </span>
        )}
      </span>

      <SpeedControl speed={speed} keepsPitch={keepsPitch} onSpeed={onSpeed} />

      <span className={styles.hint}>←→ 1 s · ⇧←→ 5 s · 0–9 saltar</span>
    </div>
  );
}

/** Dibujado y no un carácter: ▶ sale como emoji en macOS. */
function PlayGlyph({ playing }: { playing: boolean }) {
  return (
    <svg className={styles.glyph} viewBox="0 0 10 10" aria-hidden>
      {playing ? (
        <>
          <rect x="1.5" y="1" width="2.5" height="8" />
          <rect x="6" y="1" width="2.5" height="8" />
        </>
      ) : (
        <path d="M2 1 L9 5 L2 9 Z" />
      )}
    </svg>
  );
}
