"use client";

import type { Chord } from "@/lib/api";
import { formatChord } from "@/lib/chords";

import styles from "./studio.module.css";

interface Props {
  chords: Chord[];
  duration: number;
  time: number;
  onSeek: (second: number) => void;
}

/**
 * Cada acorde ocupa un bloque proporcional a su duración real. Vive dentro
 * del mismo lienzo que las ondas, así que comparte eje sin más cálculo.
 * Solo uno puede estar encendido a la vez.
 */
export function ChordLane({ chords, duration, time, onSeek }: Props) {
  if (duration <= 0 || chords.length === 0) {
    return <div className={styles.chordLane} />;
  }

  return (
    <div className={styles.chordLane}>
      {chords.map((chord) => {
        const playing = time >= chord.start && time < chord.end;
        const width = ((chord.end - chord.start) / duration) * 100;

        return (
          <button
            key={`${chord.start}-${chord.chord}`}
            type="button"
            className={`${styles.chord} ${playing ? styles.chordPlaying : ""}`}
            style={{ width: `${width}%` }}
            title={`${formatChord(chord.chord)} · ${chord.start.toFixed(2)}s`}
            onClick={(event) => {
              // Sin esto el clic sube al lienzo, que saltaría a la coordenada
              // pulsada en vez de al inicio exacto del acorde.
              event.stopPropagation();
              onSeek(chord.start);
            }}
          >
            {/* "N" es ausencia de armonía detectable: no se etiqueta. */}
            {chord.chord === "N" ? "" : formatChord(chord.chord)}
          </button>
        );
      })}
    </div>
  );
}
