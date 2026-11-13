"use client";

import { type CSSProperties, useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  createProject,
  createProjectFromYoutube,
  deleteProject,
  getProject,
  keepAlive,
  listProjects,
  type Project,
  type ProjectSummary,
} from "@/lib/api";
import { LINK_FIELD_ID, ProjectsScreen } from "@/components/ProjectsScreen";
import { Studio } from "@/components/Studio";
import { TuningNotice } from "@/components/TuningNotice";
import { UpdateNotice } from "@/components/UpdateNotice";
import { AlertIcon, FileIcon, Logo } from "@/components/icons";
import styles from "@/components/projects.module.css";
import { formatDuration, isUnfinished, stageText } from "@/lib/projects";
import { stemNames } from "@/lib/stems";
import { readString, useStoredString, writeString } from "@/lib/storage";
import { formatCents, isDetuned, referencePitch } from "@/lib/tuning";

/** Preferencias del usuario, no datos: sobreviven a cerrar la app. */
const LAST_PROJECT = "mewsplit.lastProject";
const SIX_STEMS = "mewsplit.sixStems";
/** Proyectos cuyo aviso de afinación ya se leyó, separados por comas. */
const TUNING_SEEN = "mewsplit.tuningSeen";

/** Mientras algo se descarga o se analiza, la lista se refresca para mostrar el avance. */
const POLL_MS = 1000;

/** Lo que se puede soltar sobre la ventana: un audio o un enlace arrastrado desde el navegador. */
const DROPPABLE = ["Files", "text/uri-list"];

export default function Page() {
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  // null es la pantalla de proyectos.
  const [openId, setOpenId] = useState<string | null>(null);
  // La canción elegida en la biblioteca; al volver del estudio es la que estaba abierta.
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loaded, setLoaded] = useState<Project | null>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sixStems = useStoredString(SIX_STEMS) === "1";
  const tuningSeenList = useStoredString(TUNING_SEEN);
  const tuningSeen = useMemo(() => tuningSeenList?.split(",").filter(Boolean) ?? [], [tuningSeenList]);

  useEffect(() => keepAlive(), []);

  const refresh = useCallback(async () => {
    const list = await listProjects();
    setProjects(list);
    return list;
  }, []);

  // Al abrir, vuelve donde se dejó: el proyecto abierto o la pantalla de proyectos.
  useEffect(() => {
    let alive = true;
    listProjects()
      .then((list) => {
        if (!alive) return;
        setProjects(list);
        const last = readString(LAST_PROJECT);
        const found = list.find((p) => p.id === last)?.id ?? null;
        setOpenId(found);
        setSelectedId(found);
      })
      .catch((e) => alive && setError(message(e)));
    return () => {
      alive = false;
    };
  }, []);

  const working = projects?.some(isUnfinished);
  useEffect(() => {
    if (!working) return;
    const id = setInterval(() => refresh().catch(() => {}), POLL_MS);
    return () => clearInterval(id);
  }, [working, refresh]);

  const opened = useMemo(
    () => projects?.find((p) => p.id === openId) ?? null,
    [projects, openId],
  );

  // El detalle (acordes, stems) se pide una sola vez por proyecto, cuando está
  // listo, y no al reabrirlo: un objeto nuevo haría que Studio volviera a
  // cargar los stems. Un proyecto terminado ya no cambia.
  const detailId = openId && opened?.status === "done" ? openId : null;
  const project = loaded?.id === detailId ? loaded : null;
  const loadedId = loaded?.id;
  useEffect(() => {
    if (!detailId || detailId === loadedId) return;
    let alive = true;
    getProject(detailId)
      .then((detail) => alive && setLoaded(detail))
      .catch((e) => alive && setError(message(e)));
    return () => {
      alive = false;
    };
  }, [detailId, loadedId]);

  function open(id: string | null) {
    setError(null);
    setOpenId(id);
    if (id) setSelectedId(id);
    writeString(LAST_PROJECT, id);
  }

  /** Crea el proyecto y lo abre. Devuelve si se creó. */
  async function start(request: () => Promise<Project>): Promise<boolean> {
    setError(null);
    try {
      const created = await request();
      await refresh();
      open(created.id);
      return true;
    } catch (e) {
      setError(message(e));
      return false;
    }
  }

  const fromFile = (file: File) => start(() => createProject(file, { sixStems }));
  const fromLink = (url: string) => start(() => createProjectFromYoutube(url, { sixStems }));

  async function remove(id: string) {
    setError(null);
    try {
      await deleteProject(id);
      await refresh();
    } catch (e) {
      setError(message(e));
    }
  }

  function dismissTuning(id: string) {
    // Solo se recuerdan los proyectos que siguen existiendo: la lista no crece sin fin.
    const alive = new Set((projects ?? []).map((p) => p.id));
    const seen = [...tuningSeen.filter((x) => alive.has(x)), id];
    writeString(TUNING_SEEN, seen.join(","));
  }

  function chooseSixStems(value: boolean) {
    writeString(SIX_STEMS, value ? "1" : "0");
  }

  // Soltar un audio o un enlace en cualquier parte de la ventana crea un proyecto.
  // Texto suelto no cuenta: arrastrarlo dentro del campo del enlace es editarlo.
  const dragDepth = useRef(0);
  const droppable = (e: React.DragEvent) => e.dataTransfer.types.some((type) => DROPPABLE.includes(type));
  const dropHandlers = {
    onDragEnter: (e: React.DragEvent) => {
      if (!droppable(e)) return;
      dragDepth.current += 1;
      setDragging(true);
    },
    onDragLeave: () => {
      dragDepth.current = Math.max(0, dragDepth.current - 1);
      if (dragDepth.current === 0) setDragging(false);
    },
    onDragOver: (e: React.DragEvent) => {
      if (droppable(e)) e.preventDefault();
    },
    onDrop: (e: React.DragEvent) => {
      if (!droppable(e)) return;
      e.preventDefault();
      dragDepth.current = 0;
      setDragging(false);
      const file = e.dataTransfer.files?.[0];
      if (file) {
        void fromFile(file);
        return;
      }
      const link = droppedLink(e.dataTransfer);
      if (link) void fromLink(link);
    },
  };

  function addSong() {
    open(null);
    // El campo del enlace vive en la pantalla del repertorio: se enfoca ya montada.
    requestAnimationFrame(() => document.getElementById(LINK_FIELD_ID)?.focus());
  }

  return (
    <main className="frame" {...dropHandlers}>
      <header className="top">
        {opened ? (
          <button type="button" className="brand" onClick={() => open(null)} title="Volver al repertorio">
            <Logo />
            mewsplit
          </button>
        ) : (
          <span className="brand">
            <Logo />
            mewsplit
          </span>
        )}
        <div className="top-actions">
          {error && <span className={`error ${styles.topError}`}>{error}</span>}
          <button type="button" className="button" onClick={addSong}>
            Añadir canción
          </button>
        </div>
      </header>

      <section className="sheet">
        {opened && (
          <div className="sheet-head">
            <button type="button" className={styles.crumb} onClick={() => open(null)}>
              Repertorio /
            </button>
            <h1 className={styles.title} title={opened.name}>
              {opened.name}
            </h1>
            {project && (
              <span className="chip" title={project.device ? `Separada en ${project.device}` : undefined}>
                {projectMeta(project)}
              </span>
            )}
            {project && isDetuned(project.tuning_cents) && tuningSeen.includes(project.id) && (
              <span
                className={styles.tuningNotice}
                title={`Esta grabación no está afinada a La 440: está ${formatCents(
                  project.tuning_cents,
                )} ${project.tuning_cents > 0 ? "más aguda" : "más grave"}. Los acordes ya lo tienen en cuenta. Para tocar encima, afina tu instrumento a La = ${referencePitch(
                  project.tuning_cents,
                ).toFixed(1)} Hz.`}
              >
                Grabación desafinada {formatCents(project.tuning_cents)} · afina a La ={" "}
                {referencePitch(project.tuning_cents).toFixed(1)} Hz
              </span>
            )}
          </div>
        )}

        <div className="sheet-body">
          {projects !== null && !opened && <UpdateNotice />}

          {project?.id === openId &&
            project.status === "done" &&
            isDetuned(project.tuning_cents) &&
            !tuningSeen.includes(project.id) && (
              <TuningNotice cents={project.tuning_cents} onDismiss={() => dismissTuning(project.id)} />
            )}

          {content()}
        </div>

        {dragging && (
          <div className={styles.dropHint}>
            <FileIcon />
            <strong>Suelta para añadir la canción</strong>
            <span className="muted">Un archivo de audio o un enlace de YouTube</span>
          </div>
        )}
      </section>
    </main>
  );

  function content() {
    if (projects === null) return null;

    if (!opened) {
      return (
        <ProjectsScreen
          projects={projects}
          sixStems={sixStems}
          onSixStems={chooseSixStems}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onOpen={open}
          onFile={(file) => void fromFile(file)}
          onLink={fromLink}
          onDelete={(id) => void remove(id)}
        />
      );
    }

    if (opened.status === "error") {
      return (
        <div className={styles.status}>
          <div className={styles.failure}>
            <AlertIcon />
            <div>
              <strong>No se pudo preparar esta canción</strong>
              <p className="error">{opened.error ?? "El análisis falló."}</p>
            </div>
          </div>
          <div className={styles.statusActions}>
            <button type="button" className="button" onClick={() => open(null)}>
              Volver al repertorio
            </button>
            <button
              type="button"
              className="button danger"
              onClick={() => {
                open(null);
                void remove(opened.id);
              }}
            >
              Eliminar y empezar de nuevo
            </button>
          </div>
        </div>
      );
    }

    if (opened.status !== "done") {
      return (
        <div className={styles.status}>
          <strong className={styles.statusTitle}>{stageText(opened)}</strong>
          <div className={styles.bar}>
            <span style={{ "--progress-width": `${Math.round(opened.progress * 100)}%` } as CSSProperties} />
          </div>
          <p className="muted">Sigue en segundo plano aunque vuelvas al repertorio.</p>
          <div className={styles.statusActions}>
            <button type="button" className="button" onClick={() => open(null)}>
              Volver al repertorio
            </button>
          </div>
        </div>
      );
    }

    // key: cada proyecto tiene su propio mezclador; cambiar de proyecto lo
    // desmonta y libera el anterior.
    return project?.id === opened.id ? <Studio key={project.id} job={project} /> : null;
  }
}

/** El primer enlace de lo soltado; en text/uri-list las líneas con # son comentarios. */
function droppedLink(data: DataTransfer): string | null {
  const link = data
    .getData("text/uri-list")
    .split(/\r?\n/)
    .find((line) => line.trim() && !line.startsWith("#"));
  return link?.trim() || null;
}

/** "4:57 · 6 stems": lo que le sirve a quien toca, no el dispositivo que separó. */
function projectMeta(project: Project): string {
  const stems = stemNames(project.stems).length;
  const parts = [project.duration ? formatDuration(project.duration) : "", stems ? `${stems} stems` : ""];
  return parts.filter(Boolean).join(" · ");
}

function message(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}
