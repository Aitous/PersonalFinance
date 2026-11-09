import { useOutletContext } from "react-router-dom";

export interface SpendingContext {
  days: number;
  setDays: (days: number) => void;
  customRange: { from: string; to: string } | null;
  setCustomRange: (range: { from: string; to: string } | null) => void;
}
export const useSpendingRange = () => useOutletContext<SpendingContext>();
