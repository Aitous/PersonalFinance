import axios from "axios";

const api = axios.create({ baseURL: "http://localhost:8000" });

export const getTransactions = (params?: Record<string, string>) =>
  api.get("/transactions", { params }).then((r) => r.data);

export const updateTransactionCategory = (id: string, category: string) =>
  api.patch(`/transactions/${id}/category`, { category }).then((r) => r.data);

export const getSubscriptions = () =>
  api.get("/subscriptions").then((r) => r.data);

export const updateSubscription = (id: string, data: object) =>
  api.patch(`/subscriptions/${id}`, data).then((r) => r.data);

export const getOverview = () =>
  api.get("/analysis/overview").then((r) => r.data);

export const getCategorySummary = () =>
  api.get("/analysis/category-summary").then((r) => r.data);

export const getSavingsTips = () =>
  api.post("/analysis/savings-tips").then((r) => r.data);

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
