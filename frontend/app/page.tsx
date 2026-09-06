"use client";

import { useState } from "react";

import { uploadAudio, waitForJob, type Job } from "@/lib/api";
import { DropZone } from "@/components/DropZone";
import { Studio } from "@/components/Studio";

export default function Page() {
  const [job, setJob] = useState<Job | null>(null);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function analyze(file: File, sixStems: boolean) {
    setError(null);
    setProcessing(true);
    setJob(null);

    try {
      const created = await uploadAudio(file, { sixStems });
      setJob(await waitForJob(created.id, setJob));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setProcessing(false);
    }
  }

  return (
    <main className="workspace">
      <header className="header">
        <span className="brand">mewsplit</span>
        <span className="data">
          {job?.duration ? `${job.duration.toFixed(1)}s` : ""}
          {job?.device ? ` · ${job.device}` : ""}
        </span>
      </header>

      {job?.status === "done" ? (
        <Studio job={job} />
      ) : (
        <DropZone onFile={analyze} disabled={processing} message={statusMessage(job, processing, error)} />
      )}
    </main>
  );
}

function statusMessage(job: Job | null, processing: boolean, error: string | null): string | null {
  if (error) return `error: ${error}`;
  if (!processing) return null;
  if (!job || job.status === "queued") return "subiendo…";

  // El progreso mide la separación, que es casi todo el tiempo de espera.
  const percent = Math.round(job.progress * 100);
  return job.chords_ready ? `separando… ${percent}% · acordes listos` : `separando… ${percent}%`;
}
