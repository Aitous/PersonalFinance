import axios from "axios";
import type { TransactionFilters } from "./transactionFilters";
import { supabase } from "../auth";

export const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000", timeout: 300000 }); // 5 min — MFA may require user interaction
api.interceptors.request.use(async (request) => {
  if (supabase) {
    const { data: { session } } = await supabase.auth.getSession();
    if (session?.access_token) request.headers.Authorization = `Bearer ${session.access_token}`;
  }
  return request;
});

export const getAccountUsage = (): Promise<{ ai_requests_used: number; ai_requests_limit: number; resets_at: string }> =>
  api.get("/account/usage").then((r) => r.data);
export const getAIConsent = (): Promise<{ accepted: boolean }> => api.get("/account/ai-consent").then((r) => r.data);
export const acceptAIConsent = () => api.post("/account/ai-consent", { accepted: true }).then((r) => r.data);
export const revokeAIConsent = () => api.delete("/account/ai-consent").then((r) => r.data);
export const exportAccountData = () => api.get("/account/export").then((r) => r.data);
export const deleteAccount = () => api.delete("/account").then((r) => r.data);
export const getAccountDeletionStatus = (): Promise<{ status: "active" | "deleting" | "deleted" }> =>
  api.get("/account/deletion-status").then((r) => r.data);

export const getTransactions = (params?: TransactionFilters & Record<string, string | undefined>) =>
  api.get("/transactions", { params }).then((r) => r.data);

export const updateTransactionCategory = (id: string, category: string) =>
  api.patch(`/transactions/${id}/category`, { category }).then((r) => r.data);

export const updateTransactionCategories = (ids: string[], category: string): Promise<{ updated: number }> =>
  api.patch("/transactions/bulk/category", { ids, category }).then((r) => r.data);

export interface TransactionProvenance {
  manual_category: boolean; enrichment_status: string | null;
  imports: Array<{ filename: string; bank: string; imported_at: string; row_number: number; status: string }>;
  enrichment_history: Array<{ mode: string; status: string; model: string | null; updated_at: string }>;
  note: string;
}
export const getTransactionProvenance = (id: string): Promise<TransactionProvenance> =>
  api.get(`/transactions/${encodeURIComponent(id)}/provenance`).then((r) => r.data);

export interface CategoryRule { id: number; merchant: string; category: string; enabled: boolean }
export const getCategoryRules = (): Promise<CategoryRule[]> => api.get("/category-rules").then((r) => r.data);
export const saveCategoryRule = (merchant: string, category: string): Promise<CategoryRule> =>
  api.post("/category-rules", { merchant, category }).then((r) => r.data);
export const setCategoryRuleEnabled = (id: number, enabled: boolean): Promise<CategoryRule> =>
  api.patch(`/category-rules/${id}`, { enabled }).then((r) => r.data);

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

export interface SubscriptionEvidence {
  id: string; date: string; description: string; amount: number; source: string; merchant_name?: string | null;
}
export interface SubscriptionRecord {
  id: string; description: string; amount: number; frequency: string; last_charged: string | null;
  active: boolean; origin: "detected" | "manual" | "legacy"; dismissed: boolean;
  amount_type: "fixed" | "variable"; average_monthly_amount: number; latest_charge_amount: number; latest_period_amount: number;
  supporting_transactions: SubscriptionEvidence[];
}

export const getSubscriptions = (): Promise<SubscriptionRecord[]> =>
  api.get("/subscriptions").then((r) => r.data);

export const updateSubscription = (id: string, data: object) =>
  api.patch(`/subscriptions/${id}`, data).then((r) => r.data);

export const createSubscription = (data: { description: string; amount: number; frequency: string }) =>
  api.post("/subscriptions", data).then((r) => r.data);

export const deleteSubscription = (id: string) =>
  api.delete(`/subscriptions/${id}`).then((r) => r.data);

export const getOverview = () =>
  api.get("/analysis/overview").then((r) => r.data);

export const getCategorySummary = (days = 90, range?: { from: string; to: string }) =>
  api.get("/analysis/category-summary", { params: range ? { date_from: range.from, date_to: range.to } : { days } }).then((r) => r.data);

export const getSavingsTips = (provider?: string, days?: number, range?: { from: string; to: string }) =>
  api.post("/analysis/savings-tips", { provider, days, ...(range ? { date_from: range.from, date_to: range.to } : {}) }).then((r) => r.data);

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

export type PlaidEnvironment = "sandbox" | "production";
export interface PlaidConfig { environment: PlaidEnvironment; configured: boolean }
export interface PlaidAccount { account_id: string; name: string; mask?: string | null; type?: string | null; subtype?: string | null }
export interface PlaidItem {
  item_id: string; environment: PlaidEnvironment; institution_id?: string | null; institution_name: string;
  accounts: PlaidAccount[]; last_sync_at: string | null; last_sync_status: string;
  sync_counts: { added: number; modified: number; removed: number };
  transaction_counts: { imported: number; duplicates: number }; created_at: string | null;
}
const plaidParams = (environment: PlaidEnvironment) => ({ params: { environment } });
export const getPlaidConfig = (environment: PlaidEnvironment): Promise<PlaidConfig> => api.get("/plaid/config", plaidParams(environment)).then((r) => r.data);
export const savePlaidConfig = (environment: PlaidEnvironment, client_id: string, secret: string): Promise<PlaidConfig> =>
  api.post("/plaid/config", { client_id, secret }, plaidParams(environment)).then((r) => r.data);
export const getPlaidItems = (environment: PlaidEnvironment): Promise<PlaidItem[]> => api.get("/plaid/items", plaidParams(environment)).then((r) => r.data);
export const createPlaidLinkToken = (environment: PlaidEnvironment): Promise<{ link_token: string; environment: PlaidEnvironment }> =>
  api.post("/plaid/link-token", {}, plaidParams(environment)).then((r) => r.data);
export const exchangePlaidPublicToken = (environment: PlaidEnvironment, public_token: string) =>
  api.post("/plaid/exchange", { public_token }, plaidParams(environment)).then((r) => r.data);
export const syncPlaidItem = (environment: PlaidEnvironment, itemId: string) =>
  api.post(`/plaid/items/${encodeURIComponent(itemId)}/sync`, {}, plaidParams(environment)).then((r) => r.data);
export const removePlaidItem = (environment: PlaidEnvironment, itemId: string) =>
  api.delete(`/plaid/items/${encodeURIComponent(itemId)}`, plaidParams(environment)).then((r) => r.data);

export interface SearchPagination { offset?: number; limit?: number }
export interface TransactionSearchHit {
  id: string;
  source: string;
  date: string;
  description: string;
  amount: number;
  category: string;
  merchant_name?: string | null;
  merchant_type?: string | null;
  city?: string | null;
  is_online?: boolean | null;
  is_subscription?: boolean;
  match_type?: string;
  [key: string]: unknown;
}
export interface TransactionSearchResult {
  results: TransactionSearchHit[];
  mode: string;
  total_results: number;
  embedded_count?: number;
  stale_embedding_count?: number;
  total_transactions?: number;
  index_status?: string;
}

export const searchTransactions = (
  q: string,
  mode = "hybrid",
  filters?: TransactionFilters & Record<string, string | undefined>,
  pagination?: SearchPagination,
): Promise<TransactionSearchResult> =>
  api.get("/search", { params: { ...filters, ...pagination, q, mode } }).then((r) => r.data);

export const triggerEmbedding = () =>
  api.post("/search/embed").then((r) => r.data);

export const importFromFolder = () =>
  api.post("/import/folder").then((r) => r.data);

export interface ImportInboxFile {
  filename: string;
  bank_guess: string | null;
  size_bytes: number;
  modified_at: string;
  too_large: boolean;
  already_imported: boolean;
}
export interface ImportInboxListing { folder: string; files: ImportInboxFile[] }
export interface InboxTransactionSample { date: string; description: string; amount: number; category: string }
export interface InboxPreview extends Omit<ImportSummary, "tx_count" | "total_parsed"> {
  filename: string;
  checksum: string;
  sample_transactions: InboxTransactionSample[];
}
export const getImportInbox = (): Promise<ImportInboxListing> =>
  api.get("/import/inbox").then((r) => r.data);
export const previewImportInbox = (filename: string, bank?: string, accountId?: string): Promise<InboxPreview> =>
  api.post("/import/inbox/preview", { filename, bank, account_id: accountId || null }).then((r) => r.data);
export const confirmImportInbox = (payload: { filename: string; bank: string; account_id?: string; checksum: string }): Promise<ImportSummary> =>
  api.post("/import/inbox/confirm", { ...payload, account_id: payload.account_id || null }).then((r) => r.data);

export const getInsights = (merchantDays = 90, range?: { from: string; to: string }) =>
  api.get("/analysis/insights", { params: range ? { date_from: range.from, date_to: range.to } : { merchant_days: merchantDays } }).then((r) => r.data);

export const triggerEnrichment = () =>
  api.post("/import/enrich", null, { params: { new_only: true } }).then((r) => r.data);

export const getEnrichStatus = (mode?: "enrich" | "recategorize") =>
  api.get("/import/enrich/status", { params: { mode } }).then((r) => r.data);

export const getEnrichJob = (id: string) =>
  api.get(`/import/enrich/jobs/${encodeURIComponent(id)}`).then((r) => r.data);

export const resumeEnrichJob = (id: string) =>
  api.post(`/import/enrich/jobs/${encodeURIComponent(id)}/resume`).then((r) => r.data);

export const triggerRecategorize = () =>
  api.post("/import/recategorize").then((r) => r.data);

export const redetectSubscriptions = () =>
  api.post("/subscriptions/redetect").then((r) => r.data);

export interface BankAccount { id: string; bank: string; name: string; last4?: string | null }
export interface DataQualitySource { source: string; transaction_count: number; first_date: string | null; last_date: string | null }
export interface DataQuality {
  sources: DataQualitySource[]; total_transactions: number; missing_city: number;
  missing_merchant: number; missing_category: number; enrichment_fallback: number;
  unassigned_account: number; coverage_note: string;
}
export interface ImportBatchSummary {
  id: string; bank: string; account_id: string | null; filename: string; status: string;
  input_rows: number; parsed_rows: number; rejected_rows: number; duplicate_rows: number;
  new_transactions: number; from_date: string | null; to_date: string | null; created_at: string;
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
export const getImportBatches = (limit = 6): Promise<ImportBatchSummary[]> =>
  api.get("/import/batches", { params: { limit } }).then((r) => r.data);

export interface TransactionQuestionResult {
  question: string; answer: string; analysis_mode?: "sql" | "transactions"; criteria: Record<string, string | number | null>;
  match_count: number; gross_purchases: number; refunds: number; truncated: boolean;
  comparison: TransactionQuestionComparison | null;
  tool_steps?: string[];
  tool_results?: TransactionQuestionToolEvidence[];
  displayed_count: number;
  coverage: {
    observed_from: string | null;
    observed_through: string | null;
    complete_statement_periods: false;
    note: string;
  };
  transactions: TransactionQuestionRow[];
}
export interface TransactionQuestionRow {
  id: string; date: string; description: string; kind?: string | null; merchant_name?: string | null;
  city?: string | null; category?: string | null; amount: number; source: string;
}
export type TransactionQuestionComparison = TransactionQuestionCriteriaComparison | TransactionQuestionSqlComparison;
export interface TransactionQuestionCriteriaComparison {
  source?: "transactions";
  criteria: Record<string, string | number | null>; match_count: number;
  gross_purchases: number; refunds: number; net_spending: number;
  transactions?: TransactionQuestionRow[]; displayed_count?: number; truncated?: boolean;
  left?: TransactionQuestionAggregateFacts;
  net_spending_delta_right_minus_left?: number;
}
export interface TransactionQuestionSqlComparison {
  source: "sql";
  evidence: { sql: string };
  rows: Array<Record<string, unknown>>;
  columns: string[];
}
export interface TransactionQuestionAggregateFacts {
  matching_transaction_count: number; gross_purchases: number; refunds: number; net_spending: number;
}
export interface TransactionQuestionToolEvidence {
  tool: string;
  result: {
    dataset_id?: string;
    criteria?: Record<string, string | number | null>;
    facts?: TransactionQuestionAggregateFacts;
    group_by?: string;
    groups?: Array<{ name: string; matching_transaction_count: number; gross_purchases: number; refunds: number; net_spending: number }>;
    truncated?: boolean;
    observed_from?: string | null;
    observed_through?: string | null;
    scope_dataset_id?: string | null;
    transactions_missing_city_in_scope?: number;
    transactions_missing_city_in_full_dataset?: number;
    complete_city_coverage?: boolean;
    complete_statement_periods?: boolean;
    note?: string;
    left_criteria?: Record<string, string | number | null>;
    right_criteria?: Record<string, string | number | null>;
    left_facts?: TransactionQuestionAggregateFacts;
    right_facts?: TransactionQuestionAggregateFacts;
    net_spending_delta_right_minus_left?: number;
    columns?: string[];
    rows?: Array<Record<string, unknown>>;
    row_count?: number;
    evidence?: { sql?: string; python?: string; code?: string; output?: string };
  };
}
export interface TransactionQuestionContext {
  question: string; answer: string; criteria: Record<string, string | number | null>;
  match_count: number; gross_purchases: number; refunds: number;
}
export const askTransactions = (
  question: string,
  history: TransactionQuestionContext[] = [],
): Promise<TransactionQuestionResult> =>
  api.post("/analysis/ask", { question, history }).then((r) => r.data);

export const uploadCSV = (bank: string, file: File, accountId?: string) => {
  const form = new FormData();
  form.append("file", file);
  const params = new URLSearchParams({ bank });
  if (accountId) params.set("account_id", accountId);
  return api.post(`/import/upload?${params.toString()}`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  }).then((r) => r.data as ImportSummary);
};
