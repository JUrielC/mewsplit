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
    <div className={styles.updateBanner} role="status">
      <div className={styles.updateRow}>
        <span className={styles.tuningHeadline}>
          {mode === "updated" ? `mewsplit se actualizó a ${info.current_version}` : `mewsplit ${latest} disponible`}
        </span>
        <span className="label">
          {mode === "updated" ? `antes tenías la ${info.updated_from}` : `tienes la ${info.current_version}`}
        </span>
        {notes.length > 0 && (
          <button
            type="button"
            className="label"
            onClick={() => setShowNotes((v) => !v)}
            aria-expanded={showNotes}
          >
            {showNotes ? "ocultar novedades" : "novedades"}
          </button>
        )}

        <span className={styles.updateActions}>{actions()}</span>
      </div>

      {showNotes && (
        <ul className={styles.updateNotes}>
          {notes.map((note) => (
            <li key={note} className="label">
              {note}
            </li>
          ))}
        </ul>
      )}

      {mode === "available" && !info.can_self_update && (
        <div className={styles.updateManual}>
          {info.self_update_unavailable_reason && (
            <span className="label">{info.self_update_unavailable_reason}</span>
          )}
          {info.install_command && (
            <>
              <span className="label">o vuelve a ejecutar el instalador:</span>
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
        <button type="button" className={`label ${styles.primary}`} onClick={later}>
          entendido
        </button>
      );
    }
    if (phase === "installing") return <span className="label">descargando mewsplit {latest}…</span>;
    if (phase === "started") {
      return <span className="label">mewsplit se cerrará y volverá a abrirse ya actualizado</span>;
    }
    return (
      <>
        {phase === "error" && <span className={`label ${styles.updateError}`}>{error}</span>}
        {info?.can_self_update && (
          <button type="button" className={`label ${styles.primary}`} onClick={install}>
            {phase === "error" ? "reintentar" : "actualizar"}
          </button>
        )}
        <button type="button" className="label" onClick={later}>
          ahora no
        </button>
        <button type="button" className={`label ${styles.hint}`} onClick={skip}>
          omitir esta versión
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
