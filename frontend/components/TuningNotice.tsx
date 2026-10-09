"use client";

import styles from "@/components/projects.module.css";
import { formatCents, referencePitch } from "@/lib/tuning";

/**
 * Aviso de grabación desafinada, a todo el ancho bajo la cabecera hasta que
 * se descarta. En la cabecera era fácil no verlo, y lo importante no es la
 * cifra sino qué hacer con ella.
 */
export function TuningNotice({ cents, onDismiss }: { cents: number; onDismiss: () => void }) {
  return (
    <div className={styles.tuningBanner} role="status">
      <span className={styles.tuningHeadline}>
        esta grabación está {formatCents(cents)} {cents > 0 ? "alta" : "baja"} respecto a la = 440
      </span>
      <span className="label">
        para tocar encima, afina a la = {referencePitch(cents).toFixed(1)} hz. los acordes ya lo
        compensan. puede ser la grabación original o una copia a la que le cambiaron el tono: si
        tienes otra versión de la canción, compárala, una copia alterada suele dar acordes menos
        fiables.
      </span>
      <button type="button" className={`label ${styles.tuningDismiss}`} onClick={onDismiss}>
        entendido
      </button>
    </div>
  );
}
