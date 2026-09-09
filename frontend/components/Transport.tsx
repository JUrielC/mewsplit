"use client";

import styles from "./studio.module.css";

interface Props {
  playing: boolean;
  time: number;
  duration: number;
  currentChord: string | null;
  onToggle: () => void;
}

export function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) seconds = 0;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${String(minutes).padStart(2, "0")}:${rest.toFixed(1).padStart(4, "0")}`;
}

export function Transport({ playing, time, duration, currentChord, onToggle }: Props) {
  return (
    <div className={styles.transport}>
      <button
        type="button"
        className="label"
        onClick={onToggle}
        title="Espacio para reproducir o pausar"
      >
        {playing ? "pausa" : "reproducir"}
      </button>

      <span className="data">
        {formatTime(time)} / {formatTime(duration)}
      </span>

      <span className={`data ${currentChord && currentChord !== "N" ? "active" : ""}`}>
        {currentChord && currentChord !== "N" ? currentChord : "—"}
      </span>

      <span className={styles.hint}>espacio · ←→ 1s · ⇧←→ 5s</span>
    </div>
  );
}
