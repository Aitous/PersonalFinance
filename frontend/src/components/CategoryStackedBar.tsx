import { useNavigate } from "react-router-dom";
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from "recharts";

const CATEGORY_COLORS: Record<string, string> = {
  dining: "#287c61",
  groceries: "#9bc68b",
  transport: "#60a5fa",
  shopping: "#34d399",
  entertainment: "#f59e0b",
  subscriptions: "#fb923c",
  health: "#f87171",
  travel: "#38bdf8",
  utilities: "#94a3b8",
  other: "#6b7280",
};

interface Props {
  data: { month: string; [category: string]: number | string }[];
  categories: string[];
}

export function CategoryStackedBar({ data, categories }: Props) {
  const navigate = useNavigate();
  const mainCats = categories.filter((c) => c !== "travel");
  const hasTravel = categories.includes("travel");

  const handleClick = (barData: any) => {
    if (barData?.activeLabel) {
      navigate(`/transactions?month=${barData.activeLabel}`);
    }
  };

  return (
    <div>
      <p style={{ fontSize: 12, color: "#9ca3af", marginBottom: 8, marginTop: 0 }}>Click a bar to see that month's transactions</p>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data} margin={{ top: 10, right: 24, bottom: 5, left: 10 }} barCategoryGap="30%"
          onClick={handleClick}
          onMouseMove={(state: any) => { if (state?.isTooltipActive) document.body.style.cursor = "pointer"; else document.body.style.cursor = "default"; }}
          onMouseLeave={() => { document.body.style.cursor = "default"; }}
        >
          <XAxis dataKey="month" tick={{ fontSize: 11, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fontSize: 11, fill: "#9ca3af" }} tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`} axisLine={false} tickLine={false} width={40} />
          <Tooltip
            contentStyle={{ background: "#1e1b4b", border: "1px solid #4c1d95", borderRadius: 8, color: "#e0e7ff" }}
            formatter={(v, name) => typeof v === "number" ? [`$${v.toFixed(2)}`, name] : [v, name]}
            labelStyle={{ color: "#a5b4fc", marginBottom: 4 }}
          />
          <Legend verticalAlign="top" wrapperStyle={{ fontSize: 12, paddingBottom: 8 }} />
          {mainCats.map((cat) => (
            <Bar key={cat} dataKey={cat} stackId="a" fill={CATEGORY_COLORS[cat] ?? "#6b7280"} radius={cat === mainCats[mainCats.length - 1] ? [3, 3, 0, 0] : [0, 0, 0, 0]} />
          ))}
          {hasTravel && (
            <Bar key="travel" dataKey="travel" stackId="a" fill={CATEGORY_COLORS.travel} radius={[3, 3, 0, 0]} />
          )}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
