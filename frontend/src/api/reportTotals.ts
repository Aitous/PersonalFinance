export interface ReportSpendSource {
  total: number;
  gross_purchases: number;
  refunds: number;
  net_spending: number;
}

export function monthlyReportTotals(report: ReportSpendSource) {
  return {
    gross: report.gross_purchases,
    refunds: report.refunds,
    net: report.net_spending,
  };
}
