import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { getEnrichJob, getEnrichStatus, triggerEnrichment } from "../api/client";
import { EnrichmentContext } from "./recategorizationContext";
import "./RecategorizationStatus.css";

interface Job {
  id?: string; status: "idle" | "pending" | "running" | "done" | "error";
  done: number; total: number; error?: string | null;
  outcomes?: { success?: number; other?: number; failed?: number; fallback?: number };
}

export function EnrichmentProvider({ children }: { children: ReactNode }) {
  const [job, setJob] = useState<Job | null>(null);
  const [starting, setStarting] = useState(false);
  const [connectionError, setConnectionError] = useState(false);
  const [startError, setStartError] = useState("");
  const [dismissed, setDismissed] = useState("");
  const inFlight = useRef(false);
  const currentJob = useRef<string | null>(null);
  const generation = useRef(0);

  const refresh = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    const requestGeneration = generation.current;
    try {
      const result: Job = currentJob.current
        ? await getEnrichJob(currentJob.current)
        : await getEnrichStatus("enrich");
      if (requestGeneration !== generation.current) return;
      setJob(result);
      if (result.status === "done" || result.status === "error") currentJob.current = null;
      setConnectionError(false);
    } catch { if (requestGeneration === generation.current) setConnectionError(true); }
    finally { inFlight.current = false; }
  }, []);

  useEffect(() => {
    void refresh();
    const interval = window.setInterval(() => void refresh(), 3000);
    return () => window.clearInterval(interval);
  }, [refresh]);

  const start = useCallback(async () => {
    setStarting(true); setStartError(""); setDismissed("");
    try {
      const result = await triggerEnrichment();
      generation.current += 1;
      currentJob.current = result.id;
      setJob({ id: result.id, status: "pending", done: 0, total: 0 });
      await refresh();
    } catch { setStartError("Could not start enrichment. Please try again."); }
    finally { setStarting(false); }
  }, [refresh]);

  const active = starting || job?.status === "pending" || job?.status === "running";
  const visible = startError || connectionError || starting || (job && job.status !== "idle" && (active || job.id !== dismissed));
  const message = startError || (starting ? "Starting enrichment…" : !job && connectionError ? "Enrichment status unavailable" : job?.status === "pending" ? "Enrichment queued" : job?.status === "running" ? "Enriching transactions" : job?.status === "error" ? "Enrichment stopped with errors" : "Enrichment complete");
  return <EnrichmentContext.Provider value={{ active: !!active, start }}>
    {visible && <div className={`recategorization-status${job?.status === "error" || startError ? " is-error" : ""}`} role="status" aria-live="polite">
      <div className="recategorization-status-text"><strong>{message}</strong>
        {job && <span>{job.done.toLocaleString()} of {job.total.toLocaleString()} processed{job.outcomes?.failed ? ` · ${job.outcomes.failed} failed` : ""}{job.outcomes?.fallback ? ` · ${job.outcomes.fallback} need review` : ""}</span>}
        {connectionError && <span>Could not refresh progress. Reconnecting…</span>}
        {job?.error && <span>{job.error}</span>}
      </div>
      {active && job && job.total > 0 && <progress max={job.total} value={job.done} aria-label="Enrichment progress" />}
      {(!active && (job || startError)) && <button type="button" onClick={() => { setStartError(""); if (job?.id) setDismissed(job.id); }}>Dismiss</button>}
    </div>}
    {children}
  </EnrichmentContext.Provider>;
}
