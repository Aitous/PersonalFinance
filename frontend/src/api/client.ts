import axios from "axios";
import type { TransactionFilters } from "./transactionFilters";

const api = axios.create({ baseURL: "http://localhost:8000", timeout: 300000 }); // 5 min — MFA may require user interaction

export const getTransactions = (params?: TransactionFilters & Record<string, string | undefined>) =>
  api.get("/transactions", { params }).then((r) => r.data);

export const updateTransactionCategory = (id: string, category: string) =>
  api.patch(`/transactions/${id}/category`, { category }).then((r) => r.data);

export interface TransactionDetailsPatch {
  merchant_name?: string | null;
  city?: string | null;
  merchant_type?: string | null;
  is_online?: boolean | null;
}

export const updateTransactionDetails = (id: string, details: TransactionDetailsPatch) =>
  api.patch(`/transactions/${id}`, details).then((r) => r.data);

export const deleteTransaction = (id: string) =>
  api.delete(`/transactions/${id}`).then((r) => r.data);

export const getSubscriptions = () =>
  api.get("/subscriptions").then((r) => r.data);

export const updateSubscription = (id: string, data: object) =>
  api.patch(`/subscriptions/${id}`, data).then((r) => r.data);

export const createSubscription = (data: { description: string; amount: number; frequency: string }) =>
  api.post("/subscriptions", data).then((r) => r.data);

export const deleteSubscription = (id: string) =>
  api.delete(`/subscriptions/${id}`).then((r) => r.data);

export const getOverview = () =>
  api.get("/analysis/overview").then((r) => r.data);

export const getCategorySummary = (days = 90) =>
  api.get("/analysis/category-summary", { params: { days } }).then((r) => r.data);

export const getSavingsTips = (provider?: string, days?: number) =>
  api.post("/analysis/savings-tips", { provider, days }).then((r) => r.data);

export const triggerSync = (bank: string, since: string) =>
  api.post("/sync", { bank, since }).then((r) => r.data);

export const saveBankCredentials = (bank: string, username: string, password: string) =>
  api.post("/settings/bank-credentials", { bank, username, password }).then((r) => r.data);

export const getConfiguredBanks = () =>
  api.get("/settings/banks").then((r) => r.data);

export const getLLMConfig = () =>
  api.get("/settings/llm").then((r) => r.data);

export const saveLLMConfig = (provider: string, api_key: string) =>
  api.post("/settings/llm", { provider, api_key }).then((r) => r.data);

export const searchTransactions = (q: string, mode = "hybrid", filters?: TransactionFilters & Record<string, string | undefined>) =>
  api.get("/search", { params: { ...filters, q, mode } }).then((r) => r.data);

export const triggerEmbedding = () =>
  api.post("/search/embed").then((r) => r.data);

export const importFromFolder = () =>
  api.post("/import/folder").then((r) => r.data);

export const getInsights = (merchantDays = 90) =>
  api.get("/analysis/insights", { params: { merchant_days: merchantDays } }).then((r) => r.data);

export const triggerEnrichment = () =>
  api.post("/import/enrich").then((r) => r.data);

export const getEnrichStatus = () =>
  api.get("/import/enrich/status").then((r) => r.data);

export const triggerRecategorize = () =>
  api.post("/import/recategorize").then((r) => r.data);

export const redetectSubscriptions = () =>
  api.post("/subscriptions/redetect").then((r) => r.data);

export interface BankAccount { id: string; bank: string; name: string; last4?: string | null }
export interface DataQualitySource { source: string; transaction_count: number; first_date: string | null; last_date: string | null }
export interface DataQuality {
  sources: DataQualitySource[]; total_transactions: number; missing_city: number;
  missing_merchant: number; unassigned_account: number; coverage_note: string;
}
export interface ImportRowError { row_number: number; reason: string }
export interface ImportSummary {
  bank: string; account_id?: string | null; input_rows: number; parsed_rows: number;
  rejected_rows: number; duplicate_rows: number; new_transactions: number;
  errors: ImportRowError[]; warnings: string[]; tx_count: number; total_parsed: number; batch_id?: string | null;
}

export const getAccounts = (): Promise<BankAccount[]> => api.get("/accounts").then((r) => r.data);
export const createAccount = (account: { bank: string; name: string; last4?: string }) =>
  api.post("/accounts", account).then((r) => r.data as BankAccount);

export const previewCSV = (bank: string, file: File, accountId?: string) => {
  const form = new FormData();
  form.append("file", file);
  const params = new URLSearchParams({ bank });
  if (accountId) params.set("account_id", accountId);
  return api.post("/import/preview?" + params.toString(), form, {
    headers: { "Content-Type": "multipart/form-data" },
  }).then((r) => r.data as ImportSummary);
};

export const getDataQuality = (): Promise<DataQuality> => api.get("/analysis/data-quality").then((r) => r.data);

export const uploadCSV = (bank: string, file: File, accountId?: string) => {
  const form = new FormData();
  form.append("file", file);
  const params = new URLSearchParams({ bank });
  if (accountId) params.set("account_id", accountId);
  return api.post(`/import/upload?${params.toString()}`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  }).then((r) => r.data as ImportSummary);
};
