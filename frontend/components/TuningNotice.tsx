"use client";

import styles from "@/components/projects.module.css";
import { formatCents, referencePitch } from "@/lib/tuning";

/**
 * Aviso de grabación desafinada, a todo el ancho de la hoja hasta que se
 * descarta. En la cabecera era fácil no verlo, y lo importante no es la
 * cifra sino qué hacer con ella.
 */
export function TuningNotice({ cents, onDismiss }: { cents: number; onDismiss: () => void }) {
  return (
    <div className={`alert ${styles.notice}`} role="status">
      <p>
        <strong>
          Grabación {formatCents(cents)} {cents > 0 ? "alta" : "baja"}.
        </strong>{" "}
        Para tocar encima, afina a <span className="data">La = {referencePitch(cents).toFixed(1)} Hz</span>; los
        acordes ya lo compensan. Si tienes otra versión de la canción, compárala: una copia a la que le
        cambiaron el tono suele dar acordes menos fiables.
      </p>
      <button type="button" className="button ghost" onClick={onDismiss}>
        Entendido
      </button>
    </div>
  );
}
