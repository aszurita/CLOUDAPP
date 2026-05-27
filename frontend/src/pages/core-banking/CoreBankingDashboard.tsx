import {
  Activity,
  ArrowUpRight,
  CreditCard,
  Database,
  Gauge,
  RefreshCw,
  Server,
  ShieldCheck,
  Table2,
  TrendingUp,
} from "lucide-react";
import type { CSSProperties } from "react";
import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { CoreBankingDashboardData, CoreBankingMixItem } from "../../api";
import { getCoreBankingDashboard } from "../../api";

const palette = ["#0f766e", "#2563eb", "#d97706", "#be123c", "#6d28d9", "#0891b2", "#4d7c0f"];

export function CoreBankingDashboard() {
  const [dashboard, setDashboard] = useState<CoreBankingDashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setRefreshing(true);
    setError(null);
    try {
      const next = await getCoreBankingDashboard();
      setDashboard(next);
    } catch {
      setError("No se pudo cargar core_banking_sim desde la API.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const timeline = useMemo(
    () =>
      (dashboard?.timeline ?? []).map((point) => ({
        ...point,
        label: formatHour(point.bucket),
      })),
    [dashboard],
  );
  const transactionTypes = useMemo(() => mixWithLabel(dashboard?.transaction_types ?? [], "transaction_type"), [dashboard]);
  const channels = useMemo(() => mixWithLabel(dashboard?.channel_mix ?? [], "channel"), [dashboard]);
  const statusMix = useMemo(() => mixWithLabel(dashboard?.status_mix ?? [], "status"), [dashboard]);
  const tableInventory = dashboard?.table_inventory ?? [];
  const overview = dashboard?.overview ?? {};
  const totalRows = tableInventory.reduce((sum, table) => sum + table.estimated_rows, 0);
  const totalSize = tableInventory.reduce((sum, table) => sum + table.size_bytes, 0);
  const movementTable = tableInventory.find((table) => table.table_name === "account_movements");
  const latestAnomaly = numberFromUnknown(dashboard?.sentinel?.anomaly_score);

  if (loading && !dashboard) {
    return (
      <section className="banking-dashboard">
        <div className="panel banking-hero">
          <div>
            <p className="eyebrow">core_banking_sim</p>
            <h2>Cargando tablero operacional</h2>
            <p>Consultando PostgreSQL localhost:5433.</p>
          </div>
          <RefreshCw className="tab-spin" size={24} aria-hidden="true" />
        </div>
      </section>
    );
  }

  if (!dashboard) {
    return (
      <section className="banking-dashboard">
        <div className="notice error">
          <Database size={18} aria-hidden="true" />
          <span>{error ?? "Dashboard no disponible."}</span>
        </div>
      </section>
    );
  }

  return (
    <section className="banking-dashboard">
      <div className="panel banking-hero">
        <div>
          <p className="eyebrow">Core Banking Command Center</p>
          <h2>{dashboard.database.name}</h2>
          <p>
            {dashboard.database.engine} · {dashboard.database.host} · schema {dashboard.database.schema} · ultima actividad{" "}
            {formatDateTime(dashboard.database.latest_activity_at)}
          </p>
        </div>
        <div className="banking-hero-actions">
          <span className="banking-live-pill">
            <Activity size={15} aria-hidden="true" />
            Live API
          </span>
          <button onClick={() => void refresh()} disabled={refreshing}>
            <RefreshCw className={refreshing ? "tab-spin" : ""} size={16} aria-hidden="true" />
            Refrescar
          </button>
        </div>
      </div>

      {error && (
        <div className="notice error">
          <Database size={18} aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      <div className="banking-metric-grid">
        <DashboardMetric label="Clientes" value={formatCompactNumber(overview.customers)} Icon={Server} tone="blue" />
        <DashboardMetric label="Cuentas activas" value={formatCompactNumber(overview.active_accounts)} Icon={CreditCard} tone="green" />
        <DashboardMetric label="Transacciones" value={formatCompactNumber(overview.transactions)} Icon={Activity} tone="cyan" />
        <DashboardMetric label="Volumen transaccional" value={formatMoney(overview.transaction_volume)} Icon={TrendingUp} tone="amber" />
        <DashboardMetric label="Balance total" value={formatMoney(overview.total_balance)} Icon={ShieldCheck} tone="rose" />
      </div>

      <div className="banking-grid">
        <article className="panel banking-chart-panel banking-wide">
          <PanelTitle title="Movimiento transaccional 24h" value={`${formatCompactNumber(sumBy(timeline, "transactions"))} eventos`} />
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={timeline} margin={{ top: 8, right: 18, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="bankingAmount" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="5%" stopColor="#0f766e" stopOpacity={0.32} />
                  <stop offset="95%" stopColor="#0f766e" stopOpacity={0.04} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#e5edf2" strokeDasharray="3 3" />
              <XAxis dataKey="label" tick={{ fontSize: 12 }} />
              <YAxis tickFormatter={formatCompactNumber} tick={{ fontSize: 12 }} width={54} />
              <Tooltip formatter={(value, name) => [name === "amount" ? formatMoney(Number(value)) : formatCompactNumber(Number(value)), name]} />
              <Area dataKey="transactions" stroke="#2563eb" strokeWidth={2} fill="url(#bankingAmount)" />
              <Area dataKey="amount" stroke="#0f766e" strokeWidth={2} fill="url(#bankingAmount)" />
            </AreaChart>
          </ResponsiveContainer>
        </article>

        <article className="panel banking-chart-panel">
          <PanelTitle title="Tipos de transaccion" value={`${transactionTypes.length} tipos`} />
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie data={transactionTypes} dataKey="records" nameKey="label" outerRadius={92} innerRadius={52} paddingAngle={2}>
                {transactionTypes.map((entry, index) => (
                  <Cell key={entry.label} fill={palette[index % palette.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(value) => formatCompactNumber(Number(value))} />
            </PieChart>
          </ResponsiveContainer>
        </article>

        <article className="panel banking-chart-panel">
          <PanelTitle title="Canales" value={`${channels.length} activos`} />
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={channels} layout="vertical" margin={{ top: 6, right: 12, left: 14, bottom: 6 }}>
              <CartesianGrid stroke="#e5edf2" strokeDasharray="3 3" />
              <XAxis type="number" tickFormatter={formatCompactNumber} tick={{ fontSize: 12 }} />
              <YAxis type="category" dataKey="label" tick={{ fontSize: 12 }} width={68} />
              <Tooltip formatter={(value) => formatCompactNumber(Number(value))} />
              <Bar dataKey="records" fill="#2563eb" radius={[0, 6, 6, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </article>

        <article className="panel banking-chart-panel">
          <PanelTitle title="Estado operativo" value={`${formatCompactNumber(sumBy(statusMix, "records"))} registros`} />
          <div className="banking-status-stack">
            {statusMix.slice(0, 6).map((item, index) => (
              <div key={`${item.domain}-${item.label}`} className="banking-status-row">
                <span style={{ background: palette[index % palette.length] }} />
                <div>
                  <strong>{item.label}</strong>
                  <small>{String(item.domain ?? "operacion")}</small>
                </div>
                <b>{formatCompactNumber(Number(item.records ?? 0))}</b>
              </div>
            ))}
          </div>
        </article>

        <article className="panel banking-chart-panel">
          <PanelTitle title="Sentinel DB AI" value={latestAnomaly === null ? "sin score" : `${Math.round(latestAnomaly * 100)}% anomaly`} />
          <div className="banking-sentinel-ring" style={{ "--score": `${Math.round((latestAnomaly ?? 0) * 100)}%` } as CSSProperties}>
            <span>{latestAnomaly === null ? "n/d" : `${Math.round(latestAnomaly * 100)}`}</span>
            <small>{String(dashboard.sentinel?.fault_label ?? "normal")}</small>
          </div>
        </article>

        <article className="panel banking-wide">
          <PanelTitle title="Inventario fisico" value={`${tableInventory.length} tablas · ${formatBytes(totalSize)}`} />
          <div className="banking-table-list">
            {tableInventory.map((table) => (
              <div key={table.table_name} className="banking-table-row">
                <span>
                  <Table2 size={15} aria-hidden="true" />
                  <strong>{table.table_name}</strong>
                </span>
                <span>{formatCompactNumber(table.estimated_rows)} filas</span>
                <span>{formatBytes(table.size_bytes)}</span>
                <span>{table.column_count} columnas</span>
              </div>
            ))}
          </div>
          {movementTable && (
            <div className="banking-footnote">
              account_movements: {formatCompactNumber(movementTable.estimated_rows)} filas vivas · {formatBytes(movementTable.size_bytes)} reservados.
            </div>
          )}
        </article>

        <article className="panel">
          <PanelTitle title="Top cuentas por balance" value={formatMoney(sumTopBalances(dashboard.top_accounts))} />
          <div className="banking-account-list">
            {dashboard.top_accounts.map((account) => (
              <div key={account.account_id} className="banking-account-row">
                <div>
                  <strong>{account.account_number}</strong>
                  <span>{account.full_name ?? "cliente n/d"} · {account.account_type} · {account.risk_profile ?? "risk n/d"}</span>
                </div>
                <b>{formatMoney(account.balance)}</b>
              </div>
            ))}
          </div>
        </article>

        <article className="panel">
          <PanelTitle title="Actividad reciente" value={`${dashboard.recent_activity.length} eventos`} />
          <div className="banking-activity-list">
            {dashboard.recent_activity.map((event) => (
              <div key={`${event.activity_type}-${event.activity_id}`} className="banking-activity-row">
                <span className="banking-activity-icon">
                  <ArrowUpRight size={15} aria-hidden="true" />
                </span>
                <div>
                  <strong>{event.operation ?? event.activity_type}</strong>
                  <small>{event.activity_type} · cuenta {event.account_id ?? "n/d"} · {formatDateTime(event.occurred_at)}</small>
                </div>
                <b>{formatMoney(event.amount ?? 0)}</b>
              </div>
            ))}
          </div>
        </article>
      </div>
    </section>
  );
}

function DashboardMetric({
  label,
  value,
  Icon,
  tone,
}: {
  label: string;
  value: string;
  Icon: typeof Activity;
  tone: "blue" | "green" | "cyan" | "amber" | "rose";
}) {
  return (
    <div className={`banking-metric banking-tone-${tone}`}>
      <span>
        <Icon size={20} aria-hidden="true" />
      </span>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
      </div>
    </div>
  );
}

function PanelTitle({ title, value }: { title: string; value: string }) {
  return (
    <div className="banking-panel-title">
      <h3>{title}</h3>
      <span>{value}</span>
    </div>
  );
}

function mixWithLabel(items: CoreBankingMixItem[], labelKey: string): Array<CoreBankingMixItem & { label: string; records: number; amount: number }> {
  return items.map((item) => ({
    ...item,
    label: String(item[labelKey] ?? "n/d"),
    records: Number(item.records ?? 0),
    amount: Number(item.amount ?? 0),
  }));
}

function sumBy(items: Array<Record<string, unknown>>, key: string) {
  return items.reduce((sum, item) => sum + Number(item[key] ?? 0), 0);
}

function sumTopBalances(accounts: CoreBankingDashboardData["top_accounts"]) {
  return accounts.reduce((sum, account) => sum + account.balance, 0);
}

function numberFromUnknown(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatCompactNumber(value: number | string | undefined | null) {
  const numeric = Number(value ?? 0);
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(numeric);
}

function formatMoney(value: number | string | undefined | null) {
  const numeric = Number(value ?? 0);
  return new Intl.NumberFormat("en-US", {
    currency: "USD",
    maximumFractionDigits: numeric >= 1_000_000 ? 1 : 0,
    notation: Math.abs(numeric) >= 1_000_000 ? "compact" : "standard",
    style: "currency",
  }).format(numeric);
}

function formatBytes(value: number | undefined | null) {
  const bytes = Number(value ?? 0);
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return "n/d";
  return new Date(value).toLocaleString();
}

function formatHour(value: string) {
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
