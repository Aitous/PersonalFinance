/** Shared URL contract for transaction views and report drilldowns. */
export interface TransactionFilters {
  q?: string;
  merchant?: string;
  month?: string;
  ids?: string;
  category?: string;
  source?: string;
  date_from?: string;
  date_to?: string;
  description?: string;
  merchant_contains?: string;
  city?: string;
  merchant_type?: string;
  min_amount?: string;
  max_amount?: string;
  is_online?: string;
  is_subscription?: string;
  tx_type?: string;
  search_mode?: string;
  sort?: string;
  sort_dir?: string;
}

const FILTER_KEYS: readonly (keyof TransactionFilters)[] = [
  "q", "merchant", "month", "ids", "category", "source", "date_from", "date_to",
  "description", "merchant_contains", "city", "merchant_type", "min_amount", "max_amount",
  "is_online", "is_subscription", "tx_type", "search_mode", "sort", "sort_dir",
];

export function readTransactionFilters(params: URLSearchParams): TransactionFilters {
  const values: TransactionFilters = {};
  const aliases: Record<keyof TransactionFilters, string[]> = {
    q: ["q", "search"], merchant: ["merchant"], month: ["month"], ids: ["ids"],
    category: ["category"], source: ["source"], date_from: ["date_from", "dateFrom"], date_to: ["date_to", "dateTo"],
    description: ["description"], merchant_contains: ["merchant_contains"], city: ["city"], merchant_type: ["merchant_type"],
    min_amount: ["min_amount"], max_amount: ["max_amount"], is_online: ["is_online"], is_subscription: ["is_subscription"],
    tx_type: ["tx_type"], search_mode: ["search_mode"], sort: ["sort"], sort_dir: ["sort_dir"],
  };
  for (const key of FILTER_KEYS) {
    const found = aliases[key].map(alias => params.get(alias)?.trim()).find(Boolean);
    if (found) values[key] = found;
  }
  return values;
}

export function writeTransactionFilters(filters: TransactionFilters): URLSearchParams {
  const params = new URLSearchParams();
  for (const key of FILTER_KEYS) {
    const value = filters[key]?.trim();
    if (!value) continue;
    if ((key === "tx_type" && value === "spending") || (key === "search_mode" && value === "hybrid") || (key === "sort" && value === "date") || (key === "sort_dir" && value === "desc")) continue;
    params.set(key, value);
  }
  return params;
}

export function transactionFiltersUrl(filters: TransactionFilters): string {
  const query = writeTransactionFilters(filters).toString();
  return query ? `/transactions?${query}` : "/transactions";
}
