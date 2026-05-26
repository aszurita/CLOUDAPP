export function SeverityBadge({ value }: { value?: string | null }) {
  const normalized = (value || "low").toLowerCase();
  const labels: Record<string, string> = {
    stable: "Estable",
    low: "Bajo",
    medium: "Atención",
    high: "Alto",
    critical: "Crítico",
    loaded: "Cargado",
    running: "Activo",
    configured: "Configurado",
    manual: "Manual",
    open: "Abierto",
    resolved: "Resuelto",
    planned: "Preparado",
    requires_manual_execution: "Manual",
    starting: "Iniciando",
    fault_running: "Fallo activo",
    workload_finishing: "Cerrando carga",
    completed: "Completado",
    failed: "Falló",
  };
  return <span className={`sentinel-severity sentinel-severity-${normalized}`}>{labels[normalized] ?? normalized.replace(/_/g, " ")}</span>;
}
