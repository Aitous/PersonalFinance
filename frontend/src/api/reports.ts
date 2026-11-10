import { api } from "./client";

export interface CategoryItem {
  name: string;
  current: number;
  prior: number;
  recent_three_month_average: number | null;
  all_data_monthly_average: number | null;
}

export interface RecentMonthActivity {
  month: string;
  observed_activity: boolean;
  transaction_count: number;
  source_counts: Record<string, number>;
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
  gross_purchases: number;
  refunds: number;
  net_spending: number;
  prev_gross_purchases: number;
  prev_refunds: number;
  prev_net_spending: number;
  prev_total: number;
  all_data_monthly_average: number | null;
  average_period_start: string | null;
  average_period_end: string | null;
  average_month_count: number;
  recent_three_months: RecentMonthActivity[];
  recent_three_months_all_observed: boolean;
  recent_three_month_average_total: number | null;
  tx_count: number;
  categories: CategoryItem[];
  merchants: MerchantItem[];
  subscriptions_due: SubscriptionDue[];
  narrative: string | null;
}

export interface CategoryExplanationEvidence {
  category: string;
  current_gross_purchases: number;
  current_transaction_count: number;
  baseline_type: string;
  baseline_month_count: number;
  baseline_observed_month_count: number;
  baseline_months_all_observed: boolean;
  baseline_months: Array<{
    month: string;
    observed_activity: boolean;
    transaction_count: number;
    source_counts: Record<string, number>;
    category_gross_purchases: number;
    category_transaction_count: number;
  }>;
  baseline_gross_purchases: number | null;
  baseline_category_median: number | null;
  baseline_category_range: [number, number] | null;
  change: number | null;
  merchant_changes: Array<{
    merchant: string;
    current_amount: number;
    current_transactions: number;
    baseline_monthly_average: number | null;
    baseline_active_month_count: number;
    baseline_month_amounts: Array<{ month: string; observed_activity: boolean; amount: number }>;
    change: number | null;
  }>;
  largest_current_transactions: Array<{
    date: string;
    merchant: string;
    description: string;
    amount: number;
  }>;
  largest_baseline_transactions: Array<{
    date: string;
    month: string;
    merchant: string;
    description: string;
    amount: number;
  }>;
}

export interface MonthlyCategoryExplanations {
  explanations: Record<string, string> | null;
  evidence?: CategoryExplanationEvidence[];
  cached: boolean;
  data_revision: number;
}

export async function getMonthlyReport(year: number, month: number): Promise<MonthlyReport> {
  const res = await api.get<MonthlyReport>("/analysis/monthly-report", { params: { year, month } });
  return res.data;
}

export async function generateNarrative(year: number, month: number): Promise<string> {
  const res = await api.post<{ narrative: string }>("/analysis/monthly-report/narrative", null, { params: { year, month } });
  return res.data.narrative;
}

export async function getCachedCategoryExplanations(
  year: number, month: number, comparison: "recent3" | "prior",
): Promise<MonthlyCategoryExplanations> {
  const res = await api.get<MonthlyCategoryExplanations>("/analysis/monthly-report/category-explanations", { params: { year, month, comparison } });
  return res.data;
}

export async function generateCategoryExplanations(
  year: number, month: number, comparison: "recent3" | "prior",
): Promise<MonthlyCategoryExplanations> {
  const key = `${year}-${month}-${comparison}`;
  const existing = categoryExplanationRequests.get(key);
  if (existing) return existing;
  const request = api.post<MonthlyCategoryExplanations>("/analysis/monthly-report/category-explanations", null, { params: { year, month, comparison } })
    .then((res) => res.data)
    .finally(() => categoryExplanationRequests.delete(key));
  categoryExplanationRequests.set(key, request);
  return request;
}

const categoryExplanationRequests = new Map<string, Promise<MonthlyCategoryExplanations>>();
