export function SeverityBadge({ value }: { value?: string | null }) {
  const normalized = (value || "low").toLowerCase();
  return <span className={`sentinel-severity sentinel-severity-${normalized}`}>{normalized.replace(/_/g, " ")}</span>;
}
