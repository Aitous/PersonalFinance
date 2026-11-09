import { useState } from "react";

const PRESETS = [
  { label: "30 days", days: 30 },
  { label: "90 days", days: 90 },
  { label: "180 days", days: 180 },
  { label: "365 days", days: 365 },
  { label: "730 days", days: 730 },
];

interface Props {
  days: number;
  setDays: (days: number) => void;
  customRange: { from: string; to: string } | null;
  setCustomRange: (range: { from: string; to: string } | null) => void;
}

export function SpendingRangePicker({ days, setDays, customRange, setCustomRange }: Props) {
  const [from, setFrom] = useState(customRange?.from ?? "");
  const [to, setTo] = useState(customRange?.to ?? "");
  const invalid = Boolean(from && to && from > to);
  const incomplete = Boolean(from) !== Boolean(to);

  function choosePreset(value: number) {
    setDays(value);
    setCustomRange(null);
  }

  function applyCustomRange() {
    if (from && to && !invalid) setCustomRange({ from, to });
  }

  const rangeLabel = customRange
    ? `${customRange.from} – ${customRange.to}`
    : `Last ${days} days`;

  return <section className="spending-range-picker" aria-label="Spending date range">
    <div className="spending-range-presets" role="group" aria-label="Preset date ranges">
      {PRESETS.map((preset) => <button
        key={preset.days}
        type="button"
        aria-pressed={!customRange && days === preset.days}
        className={!customRange && days === preset.days ? "is-active" : ""}
        onClick={() => choosePreset(preset.days)}
      >{preset.label}</button>)}
    </div>
    <div className="spending-range-custom">
      <label>From <input aria-label="Spending start date" type="date" value={from} max={to || undefined} onChange={(event) => setFrom(event.target.value)} /></label>
      <label>To <input aria-label="Spending end date" type="date" value={to} min={from || undefined} onChange={(event) => setTo(event.target.value)} /></label>
      <button type="button" onClick={applyCustomRange} disabled={!from || !to || invalid || incomplete}>Apply dates</button>
    </div>
    <span className="spending-range-current" aria-live="polite">Showing {rangeLabel}</span>
    {invalid && <span className="spending-range-error" role="alert">Start date must be on or before end date.</span>}
  </section>;
}
