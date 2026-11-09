export function toggleVisibleSelection<T extends { id: string; amount: number }>(
  selected: Record<string, T>, visible: T[], checked: boolean,
): Record<string, T> {
  const next = { ...selected };
  for (const tx of visible) {
    if (checked) next[tx.id] = tx;
    else delete next[tx.id];
  }
  return next;
}

export function selectionTotalCents(selected: Record<string, { amount: number }>): number {
  return Object.values(selected).reduce((total, tx) => total + Math.round(tx.amount * 100), 0);
}
