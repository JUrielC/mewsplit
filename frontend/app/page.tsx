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
import { ProjectsScreen } from "@/components/ProjectsScreen";
import { Studio } from "@/components/Studio";
import { TuningNotice } from "@/components/TuningNotice";
import styles from "@/components/projects.module.css";
import { isUnfinished, stageText } from "@/lib/projects";
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
  const [project, setProject] = useState<Project | null>(null);
  const [sixStems, setSixStems] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tuningSeen, setTuningSeen] = useState<string[]>([]);

  useEffect(() => keepAlive(), []);

  // Después de montar y no en el estado inicial: la build estática prerenderiza
  // la página sin localStorage, y leerlo antes haría que el HTML no coincida.
  useEffect(() => {
    setSixStems(readFlag(SIX_STEMS));
    setTuningSeen(readString(TUNING_SEEN)?.split(",").filter(Boolean) ?? []);
  }, []);

  const refresh = useCallback(async () => {
    const list = await listProjects();
    setProjects(list);
    return list;
  }, []);

  // Al abrir, vuelve donde se dejó: el proyecto abierto o la pantalla de proyectos.
  useEffect(() => {
    refresh()
      .then((list) => {
        const last = readString(LAST_PROJECT);
        setOpenId(list.find((p) => p.id === last)?.id ?? null);
      })
      .catch((e) => setError(message(e)));
  }, [refresh]);

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

  // El detalle (acordes, stems) se pide una sola vez, cuando el proyecto está
  // listo. Pedirlo en cada sondeo daría un objeto nuevo cada segundo y Studio
  // volvería a cargar los stems.
  const openedStatus = opened?.status;
  useEffect(() => {
    setProject(null);
    if (!openId || openedStatus !== "done") return;
    let alive = true;
    getProject(openId)
      .then((detail) => alive && setProject(detail))
      .catch((e) => alive && setError(message(e)));
    return () => {
      alive = false;
    };
  }, [openId, openedStatus]);

  function open(id: string | null) {
    setError(null);
    setOpenId(id);
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
    setTuningSeen(seen);
    writeString(TUNING_SEEN, seen.join(","));
  }

  function chooseSixStems(value: boolean) {
    setSixStems(value);
    writeFlag(SIX_STEMS, value);
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

  return (
    <main className="workspace" {...dropHandlers}>
      <header className="header">
        <nav className={styles.crumbs}>
          {opened ? (
            <button type="button" className="brand" onClick={() => open(null)} title="Volver a proyectos">
              mewsplit
            </button>
          ) : (
            <span className="brand">mewsplit</span>
          )}
          <span className={styles.trail}>
            {opened ? (
              <>
                <button type="button" className="label" onClick={() => open(null)}>
                  proyectos
                </button>
                <span className="label">/</span>
                <span className={styles.current} title={opened.name}>
                  {opened.name}
                </span>
              </>
            ) : (
              <span className={`label ${styles.here}`}>proyectos</span>
            )}
          </span>
        </nav>
        {project && isDetuned(project.tuning_cents) && tuningSeen.includes(project.id) && (
          <span
            className={`label ${styles.tuningNotice}`}
            title={`Esta grabación no está afinada a La 440: está ${formatCents(
              project.tuning_cents,
            )} ${project.tuning_cents > 0 ? "más aguda" : "más grave"}. Los acordes ya lo tienen en cuenta. Para tocar encima, afina tu instrumento a La = ${referencePitch(
              project.tuning_cents,
            ).toFixed(1)} Hz.`}
          >
            grabación desafinada {formatCents(project.tuning_cents)} · afina a La ={" "}
            {referencePitch(project.tuning_cents).toFixed(1)} Hz
          </span>
        )}
        <span className="data">
          {error ? <span className="active">error: {error}</span> : null}
          {!error && project?.duration ? `${project.duration.toFixed(1)}s` : ""}
          {!error && project?.device ? ` · ${project.device}` : ""}
        </span>
      </header>

      {project?.id === openId &&
        project.status === "done" &&
        isDetuned(project.tuning_cents) &&
        !tuningSeen.includes(project.id) && (
          <TuningNotice cents={project.tuning_cents} onDismiss={() => dismissTuning(project.id)} />
        )}

      {content()}

      {dragging && (
        <div className={styles.dropHint}>suelta el audio o el enlace para crear un proyecto</div>
      )}
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
          <span className="label">{opened.error ?? "el análisis falló"}</span>
          <span className="label">puedes eliminarlo desde proyectos y volver a crearlo</span>
        </div>
      );
    }

    if (opened.status !== "done") {
      return (
        <div className={styles.status}>
          <span className="label">{stageText(opened)}</span>
          <div className={styles.progressTrack}>
            <div
              className={styles.progressFill}
              style={{ "--progress-width": `${Math.round(opened.progress * 100)}%` } as CSSProperties}
            />
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

function message(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

function readString(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeString(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    // Sin almacenamiento (ventana privada, datos bloqueados) solo se pierde el recuerdo.
  }
}

function readFlag(key: string): boolean {
  return readString(key) === "1";
}

function writeFlag(key: string, value: boolean) {
  writeString(key, value ? "1" : "0");
}
