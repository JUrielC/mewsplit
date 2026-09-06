"use client";

import { toDecibels, type TrackState } from "@/lib/audio";

import styles from "./studio.module.css";

interface Props {
  track: TrackState;
  onVolume: (value: number) => void;
  onMute: () => void;
  onSolo: () => void;
}

function formatDb(volume: number, audible: boolean): string {
  if (!audible) return "mute";
  const db = toDecibels(volume);
  if (db === -Infinity) return "-inf";
  return `${db > 0 ? "+" : ""}${db.toFixed(1)}`;
}

/** Controles del canal. Quedan fijos: el scroll horizontal solo mueve el tiempo. */
export function TrackStrip({ track, onVolume, onMute, onSolo }: Props) {
  return (
    <div className={`${styles.channel} ${track.audible ? "" : styles.channelMuted}`}>
      <button
        type="button"
        className={`${styles.name} ${track.soloed ? styles.nameSoloed : ""}`}
        onClick={onSolo}
        title="Solo"
      >
        {track.name}
      </button>

      <button type="button" className={styles.readout} onClick={onMute} title="Mute">
        {formatDb(track.volume, track.audible)}
      </button>

      <input
        type="range"
        className={styles.fader}
        min={0}
        max={1}
        step={0.01}
        value={track.volume}
        onChange={(e) => onVolume(Number(e.target.value))}
        aria-label={`Volumen de ${track.name}`}
      />

      <div className={styles.toggles}>
        <button
          type="button"
          className={`${styles.toggle} ${track.soloed ? styles.toggleOn : ""}`}
          onClick={onSolo}
        >
          s
        </button>
        <button
          type="button"
          className={`${styles.toggle} ${track.muted ? styles.toggleOn : ""}`}
          onClick={onMute}
        >
          m
        </button>
      </div>
    </div>
  );
}
