import { createContext, useContext } from "react";

export interface StatusContext { active: boolean; start: () => Promise<void> }
export const RecategorizationContext = createContext<StatusContext | null>(null);
export const EnrichmentContext = createContext<StatusContext | null>(null);

export function useEnrichment() {
  const value = useContext(EnrichmentContext);
  if (!value) throw new Error("Enrichment status is unavailable");
  return value;
}

export function useRecategorization() {
  const value = useContext(RecategorizationContext);
  if (!value) throw new Error("Recategorization status is unavailable");
  return value;
}
