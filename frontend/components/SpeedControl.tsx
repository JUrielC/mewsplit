"use client";

import styles from "./studio.module.css";

/**
 * Pasos de velocidad. Más finos cerca de 1, que es donde se practica: pasar
 * de 100% a 85% o 90% es lo habitual para sacar un pasaje.
 */
export const SPEED_STEPS = [0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1, 1.05, 1.1, 1.25, 1.5];

interface Props {
  speed: number;
  /** Si es falso, el navegador no pudo cargar el corrector y el tono cambia. */
  keepsPitch: boolean;
  onSpeed: (speed: number) => void;
}

export function SpeedControl({ speed, keepsPitch, onSpeed }: Props) {
  const index = SPEED_STEPS.indexOf(speed);
  const percent = `${Math.round(speed * 100)}%`;

  return (
    <div className={styles.zoom}>
      <span className="label">velocidad</span>
      <button
        type="button"
        className="label"
        disabled={index <= 0}
        onClick={() => onSpeed(SPEED_STEPS[index - 1])}
        aria-label="Más lento"
      >
        −
      </button>
      <button
        type="button"
        className={`data ${speed !== 1 ? styles.speedChanged : ""}`}
        onClick={() => onSpeed(1)}
        title={
          keepsPitch
            ? "Clic para volver a 100%. El tono se mantiene."
            : "Clic para volver a 100%. Este navegador no puede mantener el tono al cambiar la velocidad."
        }
      >
        {percent}
      </button>
      <button
        type="button"
        className="label"
        disabled={index >= SPEED_STEPS.length - 1}
        onClick={() => onSpeed(SPEED_STEPS[index + 1])}
        aria-label="Más rápido"
      >
        +
      </button>
    </div>
  );
}
