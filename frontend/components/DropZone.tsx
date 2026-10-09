"use client";

import { useRef, type CSSProperties } from "react";

import styles from "./studio.module.css";

interface Props {
  onFile: (file: File, sixStems: boolean) => void;
  /** La elección de 4/6 stems la lleva quien la muestre también en otro sitio. */
  sixStems: boolean;
  onSixStems: (sixStems: boolean) => void;
  disabled?: boolean;
  message?: string | null;
  progress?: number | null;
}

const FORMATS = ".wav,.mp3,.flac,.aiff,.aif,.m4a,.ogg";

/**
 * El estado vacío: todavía no hay ningún proyecto.
 *
 * La elección de 4 o 6 stems se hace aquí, al cargar el audio: es una
 * decisión de separación, no un preset de mezcla. Arrastrar un audio no se
 * maneja aquí sino en toda la ventana (page.tsx): con los dos, soltarlo sobre
 * esta zona creaba el proyecto dos veces.
 */
export function DropZone({ onFile, sixStems, onSixStems, disabled, message, progress }: Props) {
  const input = useRef<HTMLInputElement>(null);

  function accept(files: FileList | null) {
    const file = files?.[0];
    if (file && !disabled) onFile(file, sixStems);
  }

  return (
    <div className={styles.dropZone}>
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
          onClick={() => onSixStems(false)}
        >
          4 stems
        </button>
        <button
          type="button"
          className={`label ${sixStems ? "active" : ""}`}
          onClick={() => onSixStems(true)}
          title="Añade guitarra y piano; degrada algo los 4 stems base"
        >
          6 stems
        </button>
      </div>

      <input ref={input} type="file" accept={FORMATS} hidden onChange={(e) => accept(e.target.files)} />
    </div>
  );
}

