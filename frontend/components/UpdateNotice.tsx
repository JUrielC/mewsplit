"use client";

import { useEffect, useState } from "react";

import { acknowledgeUpdate, getUpdates, installUpdate, skipUpdate, type UpdateInfo } from "@/lib/api";

import styles from "./projects.module.css";

/** "ahora no" vale hasta cerrar la app; "omitir esta versión" lo guarda el backend. */
const DISMISSED = "mewsplit.updateDismissed";

type Phase = "idle" | "installing" | "started" | "error";

/**
 * Versión nueva disponible, o recién instalada. Va en la pantalla de proyectos
 * y no en el estudio: avisar a mitad de una práctica estorba.
 */
export function UpdateNotice() {
  const [info, setInfo] = useState<UpdateInfo | null>(null);
  const [hidden, setHidden] = useState(false);
  const [showNotes, setShowNotes] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getUpdates()
      .then((data) => {
        setInfo(data);
        if (data.latest_version && readDismissed() === data.latest_version) setHidden(true);
      })
      .catch(() => {});
  }, []);

  if (!info || hidden) return null;
  const mode = info.updated_from ? "updated" : info.update_available && !info.skipped ? "available" : null;
  if (!mode) return null;

  const latest = info.latest_version ?? "";
  // Tras actualizar, las novedades del manifiesto son las de esta versión solo si ya es la última.
  const notes = mode === "available" || latest === info.current_version ? info.notes : [];

  function later() {
    setHidden(true);
    if (mode === "updated") {
      acknowledgeUpdate().catch(() => {});
      return;
    }
    writeDismissed(latest);
  }

  function skip() {
    setHidden(true);
    skipUpdate(latest).catch(() => {});
  }

  async function install() {
    setPhase("installing");
    setError(null);
    try {
      await installUpdate();
      setPhase("started");
      // En Windows sin WebView2 la ventana es de Edge y no se cierra con mewsplit;
      // la versión nueva abre la suya.
      if (info?.platform === "win32") setTimeout(() => window.close(), 4000);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase("error");
    }
  }

  return (
    <div className={`alert ${styles.updateBanner}`} role="status">
      <div className={styles.updateRow}>
        <p>
          {mode === "updated" ? (
            <>
              <strong>mewsplit se actualizó a {info.current_version}.</strong> Antes tenías la {info.updated_from}.
            </>
          ) : (
            <>
              <strong>mewsplit {latest}</strong> está disponible; tienes la {info.current_version}.
            </>
          )}
        </p>
        {notes.length > 0 && (
          <button
            type="button"
            className={styles.textButton}
            onClick={() => setShowNotes((v) => !v)}
            aria-expanded={showNotes}
          >
            {showNotes ? "Ocultar novedades" : "Novedades"}
          </button>
        )}

        <span className={styles.updateActions}>{actions()}</span>
      </div>

      {showNotes && (
        <ul className={styles.updateNotes}>
          {notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}

      {mode === "available" && !info.can_self_update && (
        <div className={styles.updateManual}>
          {info.self_update_unavailable_reason && <span>{info.self_update_unavailable_reason}</span>}
          {info.install_command && (
            <>
              <span>O vuelve a ejecutar el instalador:</span>
              <code className={`data ${styles.command}`}>{info.install_command}</code>
            </>
          )}
        </div>
      )}
    </div>
  );

  function actions() {
    if (mode === "updated") {
      return (
        <button type="button" className="button" onClick={later}>
          Entendido
        </button>
      );
    }
    if (phase === "installing") return <span>Descargando mewsplit {latest}…</span>;
    if (phase === "started") {
      return <span>mewsplit se cerrará y volverá a abrirse ya actualizado.</span>;
    }
    return (
      <>
        {phase === "error" && <span className="error">{error}</span>}
        {info?.can_self_update && (
          <button type="button" className="button" onClick={install}>
            {phase === "error" ? "Reintentar" : "Actualizar"}
          </button>
        )}
        <button type="button" className="button ghost" onClick={later}>
          Ahora no
        </button>
        <button type="button" className={styles.textButton} onClick={skip}>
          Omitir esta versión
        </button>
      </>
    );
  }
}

function readDismissed(): string | null {
  try {
    return sessionStorage.getItem(DISMISSED);
  } catch {
    return null;
  }
}

function writeDismissed(version: string) {
  try {
    sessionStorage.setItem(DISMISSED, version);
  } catch {
    // Sin almacenamiento solo se pierde el recuerdo: vuelve a avisar al recargar.
  }
}
