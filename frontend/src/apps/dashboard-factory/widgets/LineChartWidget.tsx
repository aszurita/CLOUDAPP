import { AlertCircle, Loader2 } from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { WidgetData, WidgetDef } from "../types";

type Props = {
  widget: WidgetDef;
  data: WidgetData | null;
  loading: boolean;
};

export function LineChartWidget({ widget, data, loading }: Props) {
  const xKey = widget.x_field ?? (data?.columns[0] ?? "x");
  const yKey = widget.y_field ?? (data?.columns[1] ?? "y");
  const chartData = data
    ? data.rows.map((row) => ({ [xKey]: row[0], [yKey]: Number(row[1]) || 0 }))
    : [];

  return (
    <div className="df-widget-card df-chart-card">
      <span className="df-widget-title">{widget.title}</span>
      {loading ? (
        <div className="df-widget-loading">
          <Loader2 size={20} className="df-spin" />
        </div>
      ) : data?.error ? (
        <div className="df-widget-error">
          <AlertCircle size={14} />
          <span>{data.error}</span>
        </div>
      ) : chartData.length === 0 ? (
        <div className="df-widget-empty">Sin datos</div>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 32 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5eaf0" />
            <XAxis
              dataKey={xKey}
              tick={{ fontSize: 11, fill: "#6b7f90" }}
              angle={-30}
              textAnchor="end"
              interval={0}
            />
            <YAxis tick={{ fontSize: 11, fill: "#6b7f90" }} width={60} />
            <Tooltip
              contentStyle={{ borderRadius: 8, border: "1px solid #dde5ec", fontSize: 12 }}
              formatter={(v: unknown) => [formatNum(v), yKey]}
            />
            <Line
              type="monotone"
              dataKey={yKey}
              stroke="#7c3aed"
              strokeWidth={2}
              dot={{ r: 3, fill: "#7c3aed" }}
              activeDot={{ r: 5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

function formatNum(v: unknown): string {
  const n = Number(v);
  if (isNaN(n)) return String(v);
  return n >= 1_000_000
    ? `${(n / 1_000_000).toFixed(1)}M`
    : n >= 1_000
    ? `${(n / 1_000).toFixed(1)}K`
    : n.toLocaleString("es-EC");
}
