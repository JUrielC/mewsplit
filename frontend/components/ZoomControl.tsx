"use client";

import styles from "./studio.module.css";

export const ZOOM_LEVELS = [1, 2, 4, 8, 12, 16, 24, 32, 48, 64, 96, 128];

interface Props {
  zoom: number;
  onZoom: (zoom: number) => void;
}

/** El zoom es un multiplicador del ancho visible, no píxeles por segundo. */
export function ZoomControl({ zoom, onZoom }: Props) {
  const index = ZOOM_LEVELS.indexOf(zoom);

  return (
    <div className={styles.stepper}>
      <span className="label">Zoom</span>
      <button
        type="button"
        className="button square"
        disabled={index <= 0}
        onClick={() => onZoom(ZOOM_LEVELS[index - 1])}
        aria-label="Alejar"
      >
        −
      </button>
      <span className={`data ${styles.stepperValue}`}>{zoom}×</span>
      <button
        type="button"
        className="button square"
        disabled={index >= ZOOM_LEVELS.length - 1}
        onClick={() => onZoom(ZOOM_LEVELS[index + 1])}
        aria-label="Acercar"
      >
        +
      </button>
    </div>
  );
}
