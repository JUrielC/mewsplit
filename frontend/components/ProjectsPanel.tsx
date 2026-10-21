"use client";

import { useRef, useState } from "react";

import type { ProjectSummary } from "@/lib/api";

import styles from "./projects.module.css";

interface Props {
  projects: ProjectSummary[];
  selectedId: string | null;
  sixStems: boolean;
  collapsed: boolean;
  onSixStems: (sixStems: boolean) => void;
  onSelect: (id: string) => void;
  onCreate: (file: File) => void;
  onDelete: (id: string) => void;
  onToggle: () => void;
}

const FORMATS = ".wav,.mp3,.flac,.aiff,.aif,.m4a,.ogg";

/**
 * La lista de proyectos, siempre a mano desde el estudio: crear uno es elegir
 * un audio, sin pasar por una pantalla de inicio.
 *
 * El proyecto elegido va en el color de texto normal y no en el acento: el
 * acento ya lo usa el acorde que está sonando.
 */
export function ProjectsPanel({
  projects,
  selectedId,
  sixStems,
  collapsed,
  onSixStems,
  onSelect,
  onCreate,
  onDelete,
  onToggle,
}: Props) {
  const input = useRef<HTMLInputElement>(null);
  // Eliminar pide confirmación en la misma fila: el confirm() del navegador
  // no existe en la ventana nativa sin programarlo aparte.
  const [confirming, setConfirming] = useState<string | null>(null);

  // Oculto no deja ni una tira: se vuelve a abrir con el nombre "mewsplit".
  if (collapsed) return null;

  return (
    <aside className={styles.panel}>
      <div className={styles.head}>
        <span className="label">proyectos</span>
        <button type="button" className="label" onClick={() => input.current?.click()}>
          + nuevo
        </button>
      </div>

      <div className={styles.stems}>
        <button
          type="button"
          className={`label ${sixStems ? "" : styles.on}`}
          onClick={() => onSixStems(false)}
        >
          4 stems
        </button>
        <button
          type="button"
          className={`label ${sixStems ? styles.on : ""}`}
          onClick={() => onSixStems(true)}
          title="Añade guitarra y piano; degrada algo los 4 stems base"
        >
          6 stems
        </button>
      </div>

      <ul className={styles.list}>
        {projects.map((project) => (
          <li
            key={project.id}
            className={`${styles.item} ${project.id === selectedId ? styles.selected : ""}`}
          >
            <button
              type="button"
              className={styles.open}
              onClick={() => onSelect(project.id)}
              title={project.error ?? project.name}
            >
              <span className={styles.name}>{project.name}</span>
              {confirming !== project.id && <span className="data">{describe(project)}</span>}
            </button>

            {confirming === project.id ? (
              <span className={styles.confirm}>
                <span className="label">¿eliminar?</span>
                <button
                  type="button"
                  className="label"
                  onClick={() => {
                    setConfirming(null);
                    onDelete(project.id);
                  }}
                >
                  sí
                </button>
                <button type="button" className="label" onClick={() => setConfirming(null)}>
                  no
                </button>
              </span>
            ) : (
              <button
                type="button"
                className={`label ${styles.remove}`}
                onClick={() => setConfirming(project.id)}
                title="Eliminar proyecto"
                aria-label={`Eliminar ${project.name}`}
              >
                ×
              </button>
            )}
          </li>
        ))}
      </ul>

      <button type="button" className={`label ${styles.toggle}`} onClick={onToggle}>
        « ocultar
      </button>

      <input
        ref={input}
        type="file"
        accept={FORMATS}
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onCreate(file);
          // Sin esto, elegir otra vez el mismo archivo no dispara onChange.
          e.target.value = "";
        }}
      />
    </aside>
  );
}

function describe(project: ProjectSummary): string {
  switch (project.status) {
    case "queued":
      return "en cola";
    case "processing":
      return project.progress >= 1 ? "guardando…" : `separando ${Math.round(project.progress * 100)}%`;
    case "error":
      return "error";
    default: {
      const stems = project.model?.includes("6s") ? "6 stems" : "4 stems";
      return project.duration ? `${minutes(project.duration)} · ${stems}` : stems;
    }
  }
}

function minutes(seconds: number): string {
  const whole = Math.round(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}
