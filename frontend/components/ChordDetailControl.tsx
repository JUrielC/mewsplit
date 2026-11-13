"use client";

import type { ChordDetail } from "@/lib/chords";

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
 */
export function ChordDetailControl({ detail, onDetail }: Props) {
  return (
    <div className="segmented" role="group" aria-label="Detalle de los acordes">
      <button
        type="button"
        className="button"
        aria-pressed={detail === "simple"}
        onClick={() => onDetail("simple")}
        title="Solo mayores y menores"
      >
        Simples
      </button>
      <button
        type="button"
        className="button"
        aria-pressed={detail === "full"}
        onClick={() => onDetail("full")}
        title="Séptimas, sextas, sus, aumentados y disminuidos cuando hay evidencia sostenida"
      >
        Completos
      </button>
    </div>
  );
}
