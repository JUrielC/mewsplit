"use client";

import { type CSSProperties, useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  createProject,
  deleteProject,
  getProject,
  keepAlive,
  listProjects,
  type Project,
  type ProjectSummary,
} from "@/lib/api";
import { DropZone } from "@/components/DropZone";
import { ProjectsPanel } from "@/components/ProjectsPanel";
import { Studio } from "@/components/Studio";
import { TuningNotice } from "@/components/TuningNotice";
import styles from "@/components/projects.module.css";
import { formatCents, isDetuned, referencePitch } from "@/lib/tuning";

/** Preferencias del usuario, no datos: sobreviven a cerrar la app. */
const LAST_PROJECT = "mewsplit.lastProject";
const PANEL_COLLAPSED = "mewsplit.panelCollapsed";
const SIX_STEMS = "mewsplit.sixStems";
/** Proyectos cuyo aviso de afinación ya se leyó, separados por comas. */
const TUNING_SEEN = "mewsplit.tuningSeen";

/** Mientras algo se analiza, la lista se refresca para mostrar el avance. */
const POLL_MS = 1000;

export default function Page() {
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [sixStems, setSixStems] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tuningSeen, setTuningSeen] = useState<string[]>([]);

  useEffect(() => keepAlive(), []);

  // Después de montar y no en el estado inicial: la build estática prerenderiza
  // la página sin localStorage, y leerlo antes haría que el HTML no coincida.
  useEffect(() => {
    setCollapsed(readFlag(PANEL_COLLAPSED));
    setSixStems(readFlag(SIX_STEMS));
    setTuningSeen(readString(TUNING_SEEN)?.split(",").filter(Boolean) ?? []);
  }, []);

  const refresh = useCallback(async () => {
    const list = await listProjects();
    setProjects(list);
    return list;
  }, []);

  // Al abrir: el último proyecto que se usó, o el más nuevo.
  useEffect(() => {
    refresh()
      .then((list) => {
        const last = readString(LAST_PROJECT);
        setSelectedId(list.find((p) => p.id === last)?.id ?? list[0]?.id ?? null);
      })
      .catch((e) => setError(message(e)));
  }, [refresh]);

  const analyzing = projects?.some((p) => p.status === "queued" || p.status === "processing");
  useEffect(() => {
    if (!analyzing) return;
    const id = setInterval(() => refresh().catch(() => {}), POLL_MS);
    return () => clearInterval(id);
  }, [analyzing, refresh]);

  const selected = useMemo(
    () => projects?.find((p) => p.id === selectedId) ?? null,
    [projects, selectedId],
  );

  // El detalle (acordes, stems) se pide una sola vez, cuando el proyecto está
  // listo. Pedirlo en cada sondeo daría un objeto nuevo cada segundo y Studio
  // volvería a cargar los stems.
  const selectedStatus = selected?.status;
  useEffect(() => {
    setProject(null);
    if (!selectedId || selectedStatus !== "done") return;
    let alive = true;
    getProject(selectedId)
      .then((detail) => alive && setProject(detail))
      .catch((e) => alive && setError(message(e)));
    return () => {
      alive = false;
    };
  }, [selectedId, selectedStatus]);

  function select(id: string | null) {
    setSelectedId(id);
    writeString(LAST_PROJECT, id);
  }

  async function create(file: File, six = sixStems) {
    setError(null);
    try {
      const created = await createProject(file, { sixStems: six });
      await refresh();
      select(created.id);
    } catch (e) {
      setError(message(e));
    }
  }

  async function remove(id: string) {
    setError(null);
    try {
      await deleteProject(id);
      const list = await refresh();
      if (id === selectedId) select(list[0]?.id ?? null);
    } catch (e) {
      setError(message(e));
    }
  }

  function toggleCollapsed() {
    setCollapsed((value) => {
      writeFlag(PANEL_COLLAPSED, !value);
      return !value;
    });
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

  // Soltar un audio en cualquier parte de la ventana crea un proyecto.
  const dragDepth = useRef(0);
  const dropHandlers = {
    onDragEnter: (e: React.DragEvent) => {
      if (!e.dataTransfer.types.includes("Files")) return;
      dragDepth.current += 1;
      setDragging(true);
    },
    onDragLeave: () => {
      dragDepth.current = Math.max(0, dragDepth.current - 1);
      if (dragDepth.current === 0) setDragging(false);
    },
    onDragOver: (e: React.DragEvent) => e.preventDefault(),
    onDrop: (e: React.DragEvent) => {
      e.preventDefault();
      dragDepth.current = 0;
      setDragging(false);
      const file = e.dataTransfer.files?.[0];
      if (file) void create(file);
    },
  };

  return (
    <div className={styles.app} {...dropHandlers}>
      <ProjectsPanel
        projects={projects ?? []}
        selectedId={selectedId}
        sixStems={sixStems}
        collapsed={collapsed}
        onSixStems={chooseSixStems}
        onSelect={select}
        onCreate={(file) => void create(file)}
        onDelete={(id) => void remove(id)}
        onToggle={toggleCollapsed}
      />

      <main className="workspace">
        <header className="header">
          {/* El nombre abre y cierra el panel de proyectos: ya no hay pantalla
              de inicio a la que volver, y así el panel oculto no ocupa ancho. */}
          <button
            type="button"
            className="brand"
            onClick={toggleCollapsed}
            title={collapsed ? "Mostrar proyectos" : "Ocultar proyectos"}
            aria-expanded={!collapsed}
          >
            mewsplit
          </button>
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

        {project?.id === selectedId &&
          project.status === "done" &&
          isDetuned(project.tuning_cents) &&
          !tuningSeen.includes(project.id) && (
            <TuningNotice cents={project.tuning_cents} onDismiss={() => dismissTuning(project.id)} />
          )}

        {content()}
      </main>

      {dragging && <div className={styles.dropHint}>suelta el audio para crear un proyecto</div>}
    </div>
  );

  function content() {
    if (projects === null) return null;

    if (!selected) {
      return (
        <DropZone
          onFile={(file, six) => void create(file, six)}
          sixStems={sixStems}
          onSixStems={chooseSixStems}
        />
      );
    }

    if (selected.status === "error") {
      return (
        <div className={styles.status}>
          <span className="label">{selected.name}</span>
          <span className="label">{selected.error ?? "el análisis falló"}</span>
          <span className="label">puedes eliminarlo desde la lista y volver a crearlo</span>
        </div>
      );
    }

    if (selected.status !== "done") {
      return (
        <div className={styles.status}>
          <span className="label">{selected.name}</span>
          <span className="label">{progressText(selected)}</span>
          <div className={styles.progressTrack}>
            <div
              className={styles.progressFill}
              style={{ "--progress-width": `${Math.round(selected.progress * 100)}%` } as CSSProperties}
            />
          </div>
        </div>
      );
    }

    // key: cada proyecto tiene su propio mezclador; cambiar de proyecto lo
    // desmonta y libera el anterior.
    return project?.id === selected.id ? <Studio key={project.id} job={project} /> : null;
  }
}

function progressText(project: ProjectSummary): string {
  if (project.status === "queued") return "en cola…";
  // El avance mide la separación; al llegar al 100% aún se guardan los stems.
  if (project.progress >= 1) return "guardando el proyecto…";
  return `separando… ${Math.round(project.progress * 100)}%`;
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
