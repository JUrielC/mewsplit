"use client";

import {
  type CSSProperties,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { getProject, type Project, type ProjectSummary } from "@/lib/api";
import { formatChord } from "@/lib/chords";
import { formatDuration, isUnfinished, stageText } from "@/lib/projects";
import { stemCount, stemLabel, stemNames } from "@/lib/stems";
import { formatCents, isDetuned, referencePitch } from "@/lib/tuning";

import { FileIcon } from "./icons";
import styles from "./projects.module.css";

/** El botón "Añadir canción" de la barra superior enfoca este campo. */
export const LINK_FIELD_ID = "song-link";

interface Props {
  projects: ProjectSummary[];
  sixStems: boolean;
  onSixStems: (sixStems: boolean) => void;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onOpen: (id: string) => void;
  onFile: (file: File) => void;
  /** Devuelve si se creó el proyecto: si no, el enlace se queda para corregirlo. */
  onLink: (url: string) => Promise<boolean>;
  onDelete: (id: string) => void;
}

const FORMATS = ".wav,.mp3,.flac,.aiff,.aif,.m4a,.ogg";

type Sort = "recent" | "name" | "length";

const SORTS: { id: Sort; label: string }[] = [
  { id: "recent", label: "Recientes" },
  { id: "name", label: "A–Z" },
  { id: "length", label: "Duración" },
];

/** Los acordes que caben en la hoja del detalle. */
const SHEET_CHORDS = 16;

type StemCount = ReturnType<typeof stemCount>;

const STEM_LISTS: StemCount[] = [4, 6];

/**
 * Añadir arriba; debajo, el repertorio a la izquierda y el detalle de la
 * canción elegida a la derecha. Un clic elige y el doble clic (o Enter) abre
 * el estudio: así se puede mirar la afinación o los acordes sin cargar stems.
 *
 * La elección de 4 o 6 stems se hace aquí, al crear: es una decisión de
 * separación, no un preset de mezcla; por eso el repertorio se ve en dos
 * listas, una por cada elección. Soltar un audio o un enlace no se
 * maneja aquí sino en toda la ventana (page.tsx); la zona punteada lo indica.
 */
export function ProjectsScreen({
  projects,
  sixStems,
  onSixStems,
  selectedId,
  onSelect,
  onOpen,
  onFile,
  onLink,
  onDelete,
}: Props) {
  const input = useRef<HTMLInputElement>(null);
  const table = useRef<HTMLDivElement>(null);
  const [link, setLink] = useState("");
  const [sending, setSending] = useState(false);
  const [sort, setSort] = useState<Sort>("recent");
  const [query, setQuery] = useState("");
  const [details, setDetails] = useState<Record<string, Project>>({});
  // El id y no un booleano: al elegir otra canción la confirmación pendiente caduca sola.
  const [confirming, setConfirming] = useState<string | null>(null);

  // La lista elegida a mano vale hasta que se elige otra canción; desde ahí manda la lista de esa canción.
  const [choice, setChoice] = useState<{ stems: StemCount; selection: string | null } | null>(null);
  const selectedProject = projects.find((p) => p.id === selectedId);
  const followed = selectedProject ?? projects[0];
  const list: StemCount =
    choice && (choice.selection === selectedId || !selectedProject)
      ? choice.stems
      : followed
        ? stemCount(followed.model)
        : 4;

  // Lo que se está descargando o separando va siempre arriba, se ordene como se ordene.
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    const found = projects.filter((p) => p.name.toLowerCase().includes(q));
    const rest = found.filter((p) => !isUnfinished(p));
    if (sort === "name") rest.sort((a, b) => a.name.localeCompare(b.name, "es", { sensitivity: "base" }));
    if (sort === "length") rest.sort((a, b) => (b.duration ?? 0) - (a.duration ?? 0));
    return [...found.filter(isUnfinished), ...rest];
  }, [projects, query, sort]);

  const visible = useMemo(() => matches.filter((p) => stemCount(p.model) === list), [matches, list]);

  const selected = visible.find((p) => p.id === selectedId) ?? visible[0] ?? null;
  const detail = selected ? details[selected.id] : undefined;

  const selectedDone = selected?.status === "done" ? selected.id : null;
  useEffect(() => {
    if (!selectedDone || details[selectedDone]) return;
    let alive = true;
    getProject(selectedDone)
      .then((project) => alive && setDetails((cached) => ({ ...cached, [project.id]: project })))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [selectedDone, details]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const url = link.trim();
    if (!url) {
      document.getElementById(LINK_FIELD_ID)?.focus();
      return;
    }
    if (sending) return;
    setSending(true);
    const created = await onLink(url);
    setSending(false);
    if (created) setLink("");
  }

  // La fila con el foco manda: con Tab se puede llegar a una que no es la elegida.
  function move(event: KeyboardEvent<HTMLDivElement>) {
    const focused = (event.target as HTMLElement).closest("[data-id]")?.getAttribute("data-id");
    const current = visible.find((p) => p.id === focused) ?? selected;
    if (!current) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const index = visible.indexOf(current) + (event.key === "ArrowDown" ? 1 : -1);
      const next = visible[Math.min(visible.length - 1, Math.max(0, index))];
      onSelect(next.id);
      table.current?.querySelector<HTMLElement>(`[data-id="${next.id}"]`)?.focus();
    } else if (event.key === "Enter" && current.status === "done") {
      event.preventDefault();
      onOpen(current.id);
    }
  }

  function remove(project: ProjectSummary) {
    const index = visible.findIndex((p) => p.id === project.id);
    const neighbour = visible[index + 1] ?? visible[index - 1];
    if (neighbour) onSelect(neighbour.id);
    setConfirming(null);
    onDelete(project.id);
  }

  const done = projects.filter((p) => p.status === "done");
  const totalSeconds = done.reduce((sum, p) => sum + (p.duration ?? 0), 0);
  const totalBytes = projects.reduce((sum, p) => sum + p.size_bytes, 0);

  return (
    <div className={styles.screen}>
      <section className={styles.add} aria-labelledby="add-title">
        <h2 className={styles.heading} id="add-title">
          Añadir una canción
        </h2>
        <div className={styles.welcome}>
          <div className={styles.dropZone}>
            <FileIcon />
            <strong>Suelta aquí un archivo de audio</strong>
            <p className="muted">
              mp3, wav, flac, aiff, m4a u ogg. Cada canción sale separada en pistas, con sus acordes y un
              mezclador para tocar encima.
            </p>
            <button type="button" className="button" onClick={() => input.current?.click()}>
              Elegir archivo…
            </button>
          </div>

          <form className={styles.addForm} onSubmit={submit}>
            <div>
              <label className={styles.formLabel} htmlFor={LINK_FIELD_ID}>
                O un enlace de YouTube
              </label>
              <input
                id={LINK_FIELD_ID}
                className={`field ${styles.link}`}
                type="text"
                inputMode="url"
                placeholder="https://youtube.com/watch?v=…"
                value={link}
                onChange={(e) => setLink(e.target.value)}
                spellCheck={false}
                autoComplete="off"
              />
              <p className={styles.help}>Se descarga solo el audio; de una lista se toma el video.</p>
            </div>
            <div>
              <span className={styles.formLabel} id="stems-label">
                Pistas
              </span>
              <div className="segmented" role="group" aria-labelledby="stems-label">
                <button type="button" className="button" aria-pressed={!sixStems} onClick={() => onSixStems(false)}>
                  4 stems
                </button>
                <button type="button" className="button" aria-pressed={sixStems} onClick={() => onSixStems(true)}>
                  6 stems
                </button>
              </div>
              <p className={styles.help}>
                {sixStems
                  ? "6 stems separa además guitarra y piano; los 4 de base pierden algo de calidad."
                  : "Voz, bajo, batería y otros."}
              </p>
            </div>
            <div>
              <button type="submit" className="button primary" disabled={sending}>
                {sending ? "Creando…" : "Separar"}
              </button>
            </div>
          </form>
        </div>
      </section>

      <section className={styles.library} aria-labelledby="library-title">
        <div className={styles.toolbar}>
          <h2 className={styles.heading} id="library-title">
            Repertorio <span className="muted">· {projects.length}</span>
          </h2>
          <div className="segmented" role="group" aria-label="Lista">
            {STEM_LISTS.map((stems) => (
              <button
                key={stems}
                type="button"
                className="button"
                aria-pressed={list === stems}
                onClick={() => setChoice({ stems, selection: selectedId })}
              >
                {stems} stems
                <span className={styles.listCount}>{matches.filter((p) => stemCount(p.model) === stems).length}</span>
              </button>
            ))}
          </div>
          <div className="segmented" role="group" aria-label="Ordenar">
            {SORTS.map((option) => (
              <button
                key={option.id}
                type="button"
                className="button"
                aria-pressed={sort === option.id}
                onClick={() => setSort(option.id)}
              >
                {option.label}
              </button>
            ))}
          </div>
          {projects.length > 0 && (
            <span className={`data muted ${styles.count}`}>
              {formatDuration(totalSeconds)} · {formatSize(totalBytes)}
            </span>
          )}
          <input
            className={`field ${styles.search}`}
            type="search"
            placeholder="Buscar en el repertorio"
            aria-label="Buscar en el repertorio"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>

        <div className={styles.main}>
          <div className={styles.table} ref={table} role="listbox" aria-label="Canciones" onKeyDown={move}>
            {visible.length > 0 && (
              <div className={styles.cols} aria-hidden>
                <span>Nombre</span>
                <span className={styles.optional}>Origen</span>
                <span className={styles.num}>Duración</span>
                <span className={`${styles.num} ${styles.optional}`}>Añadida</span>
                <span className={`${styles.num} ${styles.optional}`}>Tamaño</span>
              </div>
            )}

            {visible.map((project) => (
              <button
                key={project.id}
                type="button"
                role="option"
                className={styles.row}
                aria-selected={project.id === selected?.id}
                data-id={project.id}
                title={project.name}
                onClick={() => onSelect(project.id)}
                onDoubleClick={() => project.status === "done" && onOpen(project.id)}
              >
                <span className={styles.name}>{project.name}</span>
                {project.status === "done" ? (
                  <>
                    <span className={styles.optional}>{origin(project)}</span>
                    <span className={`data ${styles.num}`}>
                      {project.duration ? formatDuration(project.duration) : "—"}
                    </span>
                    <span className={`data ${styles.num} ${styles.optional}`}>{formatDate(project.created_at)}</span>
                    <span className={`data ${styles.num} ${styles.optional}`}>{formatSize(project.size_bytes)}</span>
                  </>
                ) : (
                  <span className={`data ${styles.stage} ${isUnfinished(project) ? styles.live : "error"}`}>
                    {isUnfinished(project) ? stageText(project) : `Error · ${project.error ?? "el análisis falló"}`}
                  </span>
                )}
              </button>
            ))}

            {projects.length === 0 ? (
              <p className={styles.note}>Las canciones que añadas aparecerán aquí.</p>
            ) : visible.length > 0 ? null : query.trim() ? (
              <p className={styles.note}>
                Nada coincide con «{query.trim()}» en {list} stems.
              </p>
            ) : (
              <p className={styles.note}>Aún no hay canciones separadas en {list} stems.</p>
            )}
          </div>

          {selected && (
            <aside className={styles.detail} aria-live="polite" aria-label="Detalle">
              <div>
                <h2 className={styles.detailName}>{selected.name}</h2>
                <div className={styles.detailActions}>
                  {confirming === selected.id ? (
                    <>
                      <span className={styles.confirm}>¿Eliminar la canción y sus pistas? No se puede deshacer.</span>
                      <button type="button" className="button danger" onClick={() => remove(selected)}>
                        Eliminar
                      </button>
                      <button type="button" className="button" onClick={() => setConfirming(null)} autoFocus>
                        Cancelar
                      </button>
                    </>
                  ) : (
                    <>
                      {selected.status === "done" && (
                        <button type="button" className="button" onClick={() => onOpen(selected.id)}>
                          Abrir en el estudio
                        </button>
                      )}
                      <button type="button" className="button danger" onClick={() => setConfirming(selected.id)}>
                        Eliminar
                      </button>
                    </>
                  )}
                </div>
              </div>

              {selected.status === "done" ? (
                <DoneDetail project={selected} detail={detail} />
              ) : isUnfinished(selected) ? (
                <div>
                  <p className={styles.sectionTitle}>{stageText(selected)}</p>
                  <div className={styles.bar}>
                    <span style={progressStyle(selected)} />
                  </div>
                  <p className={styles.help}>Sigue en segundo plano; puedes abrir otra canción mientras.</p>
                </div>
              ) : (
                <p className={styles.reason}>
                  <span className="error">{sentence(selected.error ?? "El análisis falló")}</span> Elimínala y vuelve a
                  añadirla con el mismo audio o enlace.
                </p>
              )}
            </aside>
          )}
        </div>
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

/** Datos, afinación, pistas y los primeros acordes. Lo que no trae la lista llega con el detalle. */
function DoneDetail({ project, detail }: { project: ProjectSummary; detail: Project | undefined }) {
  const tuning = detail?.tuning_cents;
  const chords = detail?.chords.filter((c) => c.chord !== "N") ?? [];

  return (
    <>
      <dl className={styles.facts}>
        <Fact name="Duración">
          <span className="data">{project.duration ? formatDuration(project.duration) : "—"}</span>
        </Fact>
        <Fact name="Pistas">
          <span className="data">{stemCount(project.model)} stems</span>
        </Fact>
        <Fact name="Origen">{origin(project)}</Fact>
        <Fact name="Añadida">
          <span className="data">{formatDate(project.created_at)}</span>
        </Fact>
        <Fact name="En disco">
          <span className="data">{formatSize(project.size_bytes)}</span>
        </Fact>
        <Fact name="Afinación">
          {tuning == null ? (
            <span className="data">—</span>
          ) : (
            <>
              <span className="data">{formatCents(tuning)}</span>
              {isDetuned(tuning) && (
                <span className="muted"> · afina a La = {referencePitch(tuning).toFixed(1)} Hz</span>
              )}
            </>
          )}
        </Fact>
      </dl>

      {detail && (
        <div>
          <h3 className={styles.sectionTitle}>Pistas</h3>
          <p className={styles.stems}>
            {stemNames(detail.stems).map((name) => (
              <span key={name} className="chip">
                {stemLabel(name)}
              </span>
            ))}
          </p>
        </div>
      )}

      {chords.length > 0 && (
        <div>
          <h3 className={styles.sectionTitle}>
            Acordes
            <span className="data muted">
              {chords.length} cambios{chords.length > SHEET_CHORDS ? ` · primeros ${SHEET_CHORDS}` : ""}
            </span>
          </h3>
          <div className={styles.chart}>
            {chords.slice(0, SHEET_CHORDS).map((chord) => (
              <div key={chord.start} className={styles.cell}>
                <span className={styles.chord}>{formatChord(chord.chord)}</span>
                <span className={styles.at}>{formatDuration(Math.floor(chord.start))}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

function Fact({ name, children }: { name: string; children: ReactNode }) {
  return (
    <div className={styles.fact}>
      <dt>{name}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function progressStyle(project: ProjectSummary): CSSProperties {
  return { "--progress-width": `${Math.round(project.progress * 100)}%` } as CSSProperties;
}

/** Los errores llegan tal cual de la excepción: unos ya traen su punto y otros no. */
function sentence(text: string): string {
  return /[.!?…]$/.test(text) ? text : `${text}.`;
}

function origin(project: ProjectSummary): string {
  return project.source_url ? "YouTube" : "Archivo";
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
