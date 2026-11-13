"use client";

import { toDecibels, type TrackState } from "@/lib/audio";
import { stemLabel } from "@/lib/stems";

import styles from "./studio.module.css";

interface Props {
  track: TrackState;
  onVolume: (value: number) => void;
  onMute: () => void;
  onSolo: () => void;
}

/** "mute" solo si la pista está silenciada; apagada por el solo de otra conserva su nivel. */
function formatDb(volume: number, muted: boolean): string {
  if (muted) return "mute";
  const db = toDecibels(volume);
  if (db === -Infinity) return "-inf";
  return `${db > 0 ? "+" : ""}${db.toFixed(1)}`;
}

/** Controles del canal. Quedan fijos: el scroll horizontal solo mueve el tiempo. */
export function TrackStrip({ track, onVolume, onMute, onSolo }: Props) {
  const label = stemLabel(track.name);
  const db = formatDb(track.volume, track.muted);

  return (
    <div className={`${styles.channel} ${track.audible ? "" : styles.channelMuted}`}>
      <button
        type="button"
        className={`${styles.name} ${track.soloed ? styles.nameSoloed : ""}`}
        onClick={onSolo}
        title="Solo"
      >
        {label}
      </button>

      <button type="button" className={styles.readout} onClick={onMute} title="Silenciar">
        {db}
        {!track.muted && <span className={styles.unit}> dB</span>}
      </button>

      <input
        type="range"
        className={styles.fader}
        min={0}
        max={1}
        step={0.01}
        value={track.volume}
        onChange={(e) => onVolume(Number(e.target.value))}
        aria-label={`Volumen de ${label}`}
      />

      <div className={styles.toggles}>
        <button
          type="button"
          className={`button square ${styles.solo}`}
          aria-pressed={track.soloed}
          onClick={onSolo}
          title="Solo"
          aria-label={`Solo de ${label}`}
        >
          S
        </button>
        <button
          type="button"
          className="button square"
          aria-pressed={track.muted}
          onClick={onMute}
          title="Silenciar"
          aria-label={`Silenciar ${label}`}
        >
          M
        </button>
      </div>
    </div>
  );
}
