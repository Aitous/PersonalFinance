import axios from "axios";

const api = axios.create({ baseURL: "http://localhost:8000", timeout: 300000 }); // 5 min — MFA may require user interaction

export const getTransactions = (params?: Record<string, string | undefined>) =>
  api.get("/transactions", { params }).then((r) => r.data);

export const updateTransactionCategory = (id: string, category: string) =>
  api.patch(`/transactions/${id}/category`, { category }).then((r) => r.data);

export const getSubscriptions = () =>
  api.get("/subscriptions").then((r) => r.data);

export const updateSubscription = (id: string, data: object) =>
  api.patch(`/subscriptions/${id}`, data).then((r) => r.data);

export const getOverview = () =>
  api.get("/analysis/overview").then((r) => r.data);

export const getCategorySummary = (days = 90) =>
  api.get("/analysis/category-summary", { params: { days } }).then((r) => r.data);

export const getSavingsTips = (provider?: string) =>
  api.post("/analysis/savings-tips", { provider }).then((r) => r.data);

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

export const searchTransactions = (q: string, mode = "hybrid") =>
  api.get("/search", { params: { q, mode } }).then((r) => r.data);

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

export const redetectSubscriptions = () =>
  api.post("/subscriptions/redetect").then((r) => r.data);

export const uploadCSV = (bank: string, file: File) => {
  const form = new FormData();
  form.append("file", file);
  return api.post(`/import/upload?bank=${bank}`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  }).then((r) => r.data);
};
