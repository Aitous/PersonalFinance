import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts";

interface Props {
  data: { month: string; total: number }[];
}

export function SpendingLineChart({ data }: Props) {
  const avg = data.length ? data.reduce((s, d) => s + d.total, 0) / data.length : 0;

  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ top: 10, right: 24, bottom: 5, left: 10 }}>
        <CartesianGrid strokeDasharray="4 4" stroke="rgba(124,106,247,0.15)" vertical={false} />
        <XAxis dataKey="month" tick={{ fontSize: 11, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 11, fill: "#9ca3af" }} tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`} axisLine={false} tickLine={false} width={40} />
        <Tooltip
          contentStyle={{ background: "#1e1b4b", border: "1px solid #4c1d95", borderRadius: 8, color: "#e0e7ff" }}
          formatter={(v) => typeof v === "number" ? [`$${v.toFixed(2)}`, "Spent"] : v}
          labelStyle={{ color: "#a5b4fc", marginBottom: 4 }}
        />
        <ReferenceLine y={avg} stroke="#287c61" strokeDasharray="6 3" strokeOpacity={0.5} label={{ value: `avg $${avg.toFixed(0)}`, fill: "#287c61", fontSize: 11 }} />
        <Line type="monotone" dataKey="total" stroke="#287c61" strokeWidth={2.5} dot={{ r: 4, fill: "#287c61", strokeWidth: 0 }} activeDot={{ r: 6, fill: "#9bc68b" }} />
      </LineChart>
    </ResponsiveContainer>
  );
}
