"use client";

import { useRef, useState, type CSSProperties } from "react";

import styles from "./studio.module.css";

interface Props {
  onFile: (file: File, sixStems: boolean) => void;
  disabled?: boolean;
  message?: string | null;
  progress?: number | null;
}

const FORMATS = ".wav,.mp3,.flac,.aiff,.aif,.m4a,.ogg";

/**
 * La elección de 4 o 6 stems se hace aquí, al cargar el audio: es una
 * decisión de separación, no un preset de mezcla.
 */
export function DropZone({ onFile, disabled, message, progress }: Props) {
  const [dragging, setDragging] = useState(false);
  const [sixStems, setSixStems] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  function accept(files: FileList | null) {
    const file = files?.[0];
    if (file && !disabled) onFile(file, sixStems);
  }

  return (
    <div
      className={`${styles.dropZone} ${dragging ? styles.dropZoneActive : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        accept(e.dataTransfer.files);
      }}
    >
      <button type="button" className="label" disabled={disabled} onClick={() => input.current?.click()}>
        {message ?? "arrastra un audio o pulsa para elegir"}
      </button>

      {progress != null && (
        <div className={styles.progressTrack}>
          <div
            className={styles.progressFill}
            style={{ "--progress-width": `${Math.round(progress * 100)}%` } as CSSProperties}
          />
        </div>
      )}

      <div className={styles.options}>
        <button
          type="button"
          className={`label ${sixStems ? "" : "active"}`}
          onClick={() => setSixStems(false)}
        >
          4 stems
        </button>
        <button
          type="button"
          className={`label ${sixStems ? "active" : ""}`}
          onClick={() => setSixStems(true)}
          title="Añade guitarra y piano; degrada algo los 4 stems base"
        >
          6 stems
        </button>
      </div>

      <input ref={input} type="file" accept={FORMATS} hidden onChange={(e) => accept(e.target.files)} />
    </div>
  );
}

