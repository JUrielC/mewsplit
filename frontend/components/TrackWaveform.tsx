"use client";

import { memo, useMemo } from "react";

import styles from "./studio.module.css";

interface Props {
  peaks: Float32Array | null;
  muted: boolean;
}

/**
 * Fila de forma de onda. Vive dentro del carril desplazable, separada de los
 * controles del canal, para que el scroll horizontal mueva solo el tiempo.
 *
 * Memoizada a propósito: `Studio` se repinta en cada frame para mover el
 * playhead, y sin esto se rehacían 8000 segmentos por pista a 60 fps.
 */
export const TrackWaveform = memo(function TrackWaveform({ peaks, muted }: Props) {
  const path = useMemo(() => {
    if (!peaks || peaks.length === 0) return null;
    // Simétrica respecto al centro, con un mínimo visible en los silencios.
    return Array.from(peaks, (peak, i) => {
      const height = Math.max(peak * 0.48, 0.004);
      return `M${i},${0.5 - height} L${i},${0.5 + height}`;
    }).join(" ");
  }, [peaks]);

  return (
    <div className={`${styles.waveRow} ${muted ? styles.waveRowMuted : ""}`}>
      {path && (
        <svg
          className={styles.waveform}
          viewBox={`0 0 ${peaks!.length} 1`}
          preserveAspectRatio="none"
          aria-hidden
        >
          <path
            d={path}
            stroke="var(--text-dim)"
            strokeWidth={0.7}
            vectorEffect="non-scaling-stroke"
          />
        </svg>
      )}
    </div>
  );
});
