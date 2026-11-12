"use client";

import { type FormEvent, useRef, useState } from "react";

import type { ProjectSummary } from "@/lib/api";
import { isUnfinished, stageText } from "@/lib/projects";

import styles from "./projects.module.css";

interface Props {
  projects: ProjectSummary[];
  sixStems: boolean;
  onSixStems: (sixStems: boolean) => void;
  onOpen: (id: string) => void;
  onFile: (file: File) => void;
  /** Devuelve si se creó el proyecto: si no, el enlace se queda para corregirlo. */
  onLink: (url: string) => Promise<boolean>;
  onDelete: (id: string) => void;
}

const FORMATS = ".wav,.mp3,.flac,.aiff,.aif,.m4a,.ogg";

/**
 * Crear un proyecto arriba y los guardados debajo, como una ficha técnica:
 * el nombre de cada sección a la izquierda y su contenido a la derecha.
 *
 * La elección de 4 o 6 stems se hace aquí, al crear: es una decisión de
 * separación, no un preset de mezcla. Soltar un audio o un enlace no se
 * maneja aquí sino en toda la ventana (page.tsx).
 */
export function ProjectsScreen({
  projects,
  sixStems,
  onSixStems,
  onOpen,
  onFile,
  onLink,
  onDelete,
}: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [link, setLink] = useState("");
  const [sending, setSending] = useState(false);
  // Eliminar pide confirmación en la misma fila: el confirm() del navegador
  // no existe en la ventana nativa sin programarlo aparte.
  const [confirming, setConfirming] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const url = link.trim();
    if (!url || sending) return;
    setSending(true);
    const created = await onLink(url);
    setSending(false);
    if (created) setLink("");
  }

  const totalBytes = projects.reduce((sum, p) => sum + p.size_bytes, 0);

  return (
    <div className={styles.screen}>
      <section className={styles.section}>
        <span className="label">nuevo</span>

        <div className={styles.fields}>
          <div className={styles.field}>
            <span className={`label ${styles.fieldName}`}>archivo</span>
            <button type="button" className={`label ${styles.primary}`} onClick={() => input.current?.click()}>
              elegir un audio
            </button>
            <span className={`label ${styles.hint}`}>o arrástralo a la ventana</span>
          </div>

          <form className={styles.field} onSubmit={submit}>
            <label className={`label ${styles.fieldName}`} htmlFor="youtube-link">
              youtube
            </label>
            <input
              id="youtube-link"
              className={styles.link}
              type="text"
              inputMode="url"
              placeholder="pega un enlace"
              value={link}
              onChange={(e) => setLink(e.target.value)}
              spellCheck={false}
              autoComplete="off"
            />
            <button type="submit" className={`label ${styles.primary}`} disabled={!link.trim() || sending}>
              {sending ? "creando…" : "separar"}
            </button>
          </form>

          <div className={`${styles.field} ${styles.stems}`}>
            <span className={`label ${styles.fieldName}`}>separación</span>
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
        </div>
      </section>

      <section className={`${styles.section} ${styles.saved}`}>
        <div className={styles.sectionHead}>
          <span className="label">proyectos</span>
          {projects.length > 0 && (
            <span className="data">
              {projects.length} · {formatSize(totalBytes)}
            </span>
          )}
        </div>

        {projects.length === 0 ? (
          <span className={`label ${styles.hint}`}>aún no hay proyectos</span>
        ) : (
          <div className={styles.table}>
            <div className={`${styles.row} ${styles.columns}`} aria-hidden>
              <span className={styles.cells}>
                <span className="label">nombre</span>
                <span className="label">duración</span>
                <span className="label">stems</span>
                <span className={`label ${styles.optional}`}>origen</span>
                <span className={`label ${styles.optional}`}>fecha</span>
                <span className={`label ${styles.optional}`}>tamaño</span>
              </span>
              <span className={styles.action} />
            </div>

            <ul className={styles.list}>
              {projects.map((project) => (
                <li key={project.id} className={styles.row}>
                  <button
                    type="button"
                    className={`${styles.cells} ${styles.open}`}
                    onClick={() => onOpen(project.id)}
                    title={project.error ?? project.name}
                  >
                    <span className={styles.name}>{project.name}</span>
                    {project.status === "done" ? (
                      <>
                        <span className="data">{project.duration ? minutes(project.duration) : "—"}</span>
                        <span className="data">{project.model?.includes("6s") ? "6" : "4"}</span>
                        <span className={`data ${styles.optional}`}>
                          {project.source_url ? "youtube" : "archivo"}
                        </span>
                        <span className={`data ${styles.optional}`}>{formatDate(project.created_at)}</span>
                        <span className={`data ${styles.optional}`}>{formatSize(project.size_bytes)}</span>
                      </>
                    ) : (
                      <span className={`data ${styles.wide}`}>
                        {isUnfinished(project)
                          ? stageText(project)
                          : `error · ${project.error ?? "el análisis falló"}`}
                      </span>
                    )}
                  </button>

                  <span className={styles.action}>
                    {confirming === project.id ? (
                      <>
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
                      </>
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
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <input
        ref={input}
        type="file"
        accept={FORMATS}
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
          // Sin esto, elegir otra vez el mismo archivo no dispara onChange.
          e.target.value = "";
        }}
      />
    </div>
  );
}

function minutes(seconds: number): string {
  const whole = Math.round(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const sameYear = date.getFullYear() === new Date().getFullYear();
  return date.toLocaleDateString("es", {
    day: "numeric",
    month: "short",
    ...(sameYear ? {} : { year: "numeric" }),
  });
}

function formatSize(bytes: number): string {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
  return `${Math.round(bytes / 1e6)} MB`;
}
