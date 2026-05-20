const BASE = "http://localhost:8000";

export interface CategoryItem {
  name: string;
  current: number;
  prior: number;
}

export interface MerchantItem {
  name: string;
  total: number;
}

export interface SubscriptionDue {
  description: string;
  amount: number;
  next_date: string;
}

export interface MonthlyReport {
  year: number;
  month: number;
  total: number;
  prev_total: number;
  tx_count: number;
  categories: CategoryItem[];
  merchants: MerchantItem[];
  subscriptions_due: SubscriptionDue[];
  narrative: string | null;
}

export async function getMonthlyReport(year: number, month: number): Promise<MonthlyReport> {
  const res = await fetch(`${BASE}/analysis/monthly-report?year=${year}&month=${month}`);
  if (!res.ok) throw new Error("Failed to fetch monthly report");
  return res.json();
}

export async function generateNarrative(year: number, month: number): Promise<string> {
  const res = await fetch(
    `${BASE}/analysis/monthly-report/narrative?year=${year}&month=${month}`,
    { method: "POST" }
  );
  if (!res.ok) throw new Error("Failed to generate narrative");
  const data = await res.json();
  return data.narrative;
}
