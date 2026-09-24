"use client";

import type { ChordDetail } from "@/lib/chords";

import styles from "./studio.module.css";

interface Props {
  detail: ChordDetail;
  onDetail: (detail: ChordDetail) => void;
}

/**
 * Cuánto detalle mostrar, no cuánta precisión: las raíces y los tiempos son
 * los mismos en las dos posiciones. "Completos" añade las calidades que el
 * modelo detecta con evidencia sostenida (séptimas, sextas, sus, aug, dim);
 * "simples" las reduce a mayor o menor. No se llaman "tríadas" y "séptimas"
 * porque aug y dim también son tríadas y "completos" trae más que séptimas.
 *
 * La opción elegida va en el color de texto normal y no en el acento: el
 * acento ya lo usa el acorde que está sonando.
 */
export function ChordDetailControl({ detail, onDetail }: Props) {
  return (
    <div className={styles.detail}>
      <button
        type="button"
        className={`label ${detail === "simple" ? styles.detailOn : ""}`}
        onClick={() => onDetail("simple")}
        title="Solo mayores y menores"
      >
        simples
      </button>
      <button
        type="button"
        className={`label ${detail === "full" ? styles.detailOn : ""}`}
        onClick={() => onDetail("full")}
        title="Séptimas, sextas, sus, aumentados y disminuidos cuando hay evidencia sostenida"
      >
        completos
      </button>
    </div>
  );
}
