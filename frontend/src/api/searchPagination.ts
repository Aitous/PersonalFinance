export interface SearchPage<T> {
  results: T[];
  total_results: number;
}

export async function fetchAllSearchResults<T>(
  fetchPage: (offset: number, limit: number) => Promise<SearchPage<T>>,
  pageSize = 500,
): Promise<T[]> {
  const results: T[] = [];
  let totalResults = Number.POSITIVE_INFINITY;

  while (results.length < totalResults) {
    const page = await fetchPage(results.length, pageSize);
    totalResults = page.total_results;
    if (page.results.length === 0) break;
    results.push(...page.results);
  }

  return results;
}
