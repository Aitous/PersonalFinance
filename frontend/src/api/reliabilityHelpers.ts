export interface PreviewRequestKey {
  readonly file: object;
  readonly bank: string;
  readonly accountId: string;
}

export function previewRequestKey(file: object, bank: string, accountId: string): PreviewRequestKey {
  return { file, bank, accountId };
}

export function samePreviewRequest(a: PreviewRequestKey | null, b: PreviewRequestKey | null): boolean {
  return a !== null && b !== null && a.file === b.file && a.bank === b.bank && a.accountId === b.accountId;
}

export interface DateRange {
  date_from: string;
  date_to: string;
}

function formatDate(year: number, month: number, day: number): string {
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

export function reportPeriodRange(year: number, month: number, series: unknown): DateRange | null {
  if (series !== "current" && series !== "prior") return null;
  const offset = series === "prior" ? -1 : 0;
  const firstDay = new Date(year, month - 1 + offset, 1);
  const lastDay = new Date(firstDay.getFullYear(), firstDay.getMonth() + 1, 0).getDate();
  return {
    date_from: formatDate(firstDay.getFullYear(), firstDay.getMonth() + 1, 1),
    date_to: formatDate(firstDay.getFullYear(), firstDay.getMonth() + 1, lastDay),
  };
}

export function monthlyAverageRange(category: string, dateFrom?: string, dateTo?: string): {
  category: string;
  date_from?: string;
  date_to?: string;
} {
  return { category, ...(dateFrom ? { date_from: dateFrom } : {}), ...(dateTo ? { date_to: dateTo } : {}) };
}
