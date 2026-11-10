import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { getEnrichJob, getEnrichStatus, resumeEnrichJob, triggerRecategorize } from "../api/client";
import { RecategorizationContext } from "./recategorizationContext";
import "./RecategorizationStatus.css";

interface Job { id?: string; mode?: string; status: "idle" | "pending" | "running" | "done" | "error"; done: number; total: number; resumable?: boolean; error?: string | null; outcomes?: { failed?: number; fallback?: number; other?: number } }
export function RecategorizationProvider({ children }: { children: ReactNode }) {
  const [job, setJob] = useState<Job | null>(null);
  const [starting, setStarting] = useState(false);
  const [connectionError, setConnectionError] = useState(false);
  const [startError, setStartError] = useState("");
  const [dismissed, setDismissed] = useState(() => sessionStorage.getItem("dismissed-recategorization") || "");
  const inFlight = useRef(false);

  const refresh = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      let result: Job = await getEnrichStatus("recategorize");
      if (result.mode && result.mode !== "recategorize") {
        const knownId = sessionStorage.getItem("recategorization-job-id");
        if (!knownId) throw new Error("Re-categorization status unavailable");
        result = await getEnrichJob(knownId);
      }
      if (result.mode === "recategorize" && result.id) sessionStorage.setItem("recategorization-job-id", result.id);
      setJob(result);
      setConnectionError(false);
    } catch {
      setConnectionError(true);
    } finally { inFlight.current = false; }
  }, []);

  useEffect(() => {
    const initial = window.setTimeout(() => void refresh(), 0);
    const interval = window.setInterval(() => void refresh(), 3000);
    return () => { window.clearTimeout(initial); window.clearInterval(interval); };
  }, [refresh]);

  const start = useCallback(async () => {
    setStarting(true);
    setStartError("");
    try {
      const result = await triggerRecategorize();
      sessionStorage.setItem("recategorization-job-id", result.id);
      setDismissed("");
      sessionStorage.removeItem("dismissed-recategorization");
      setJob({ id: result.id, status: "pending", done: 0, total: 0 });
      await refresh();
    } catch {
      setStartError("Could not start re-categorization. Please try again.");
    } finally { setStarting(false); }
  }, [refresh]);

  const active = starting || job?.status === "pending" || job?.status === "running";
  const visible = startError || starting || (job && job.status !== "idle" && (active || job.id !== dismissed));
  const completed = job?.status === "done" || job?.status === "error";
  const message = startError || (starting ? "Starting re-categorization…" : job?.status === "pending" ? "Re-categorization queued" : job?.status === "running" ? "Re-categorizing transactions" : job?.status === "error" ? "Re-categorization stopped with errors" : "Re-categorization complete");

  return <RecategorizationContext.Provider value={{ active: !!active, start }}>
    {visible && <div className={`recategorization-status${job?.status === "error" || startError ? " is-error" : ""}`} role="status" aria-live="polite">
      <div className="recategorization-status-text"><strong>{message}</strong>
        {job && job.total > 0 && <span>{job.done.toLocaleString()} of {job.total.toLocaleString()} processed{job.outcomes?.failed ? ` · ${job.outcomes.failed} failed` : ""}{job.outcomes?.fallback ? ` · ${job.outcomes.fallback} fallback` : ""}{job.outcomes?.other ? ` · ${job.outcomes.other} classified as Other` : ""}</span>}
        {connectionError && <span>Could not refresh progress. Reconnecting…</span>}
        {job?.resumable && <span>No progress reported for over an hour. You can resume the unfinished transactions.</span>}
        {job?.status === "error" && job.error && <span>{job.error}</span>}
      </div>
      {active && job && job.total > 0 && <progress max={job.total} value={job.done} aria-label="Re-categorization progress" />}
      {job?.resumable && job.id && <button type="button" disabled={starting} onClick={() => { setStarting(true); setStartError(""); void resumeEnrichJob(job.id!).then(() => refresh()).catch(() => setStartError("Could not resume the job. Please try again.")).finally(() => setStarting(false)); }}>Resume job</button>}
      {(completed || !!startError) && <button type="button" aria-label="Dismiss re-categorization status" onClick={() => { setStartError(""); if (job?.id) { setDismissed(job.id); sessionStorage.setItem("dismissed-recategorization", job.id); } }}>Dismiss</button>}
    </div>}
    {children}
  </RecategorizationContext.Provider>;
}
