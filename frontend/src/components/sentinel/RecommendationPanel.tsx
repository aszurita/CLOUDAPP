import { CheckCircle2, Copy, ShieldCheck } from "lucide-react";
import { useState } from "react";

import type { CopilotResponse } from "../../api/sentinel";
import { SeverityBadge } from "./SeverityBadge";

type Props = {
  copilot: CopilotResponse | null;
  loading: boolean;
  onGenerate: () => void;
};

export function RecommendationPanel({ copilot, loading, onGenerate }: Props) {
  const [copied, setCopied] = useState<number | null>(null);

  async function copySql(sql: string, index: number) {
    await navigator.clipboard.writeText(sql);
    setCopied(index);
    window.setTimeout(() => setCopied(null), 1600);
  }

  return (
    <section className="panel sentinel-copilot-panel">
      <div className="panel-heading">
        <h2>DBA Copilot</h2>
        {copilot ? <SeverityBadge value={copilot.severity_classification} /> : <ShieldCheck size={18} />}
      </div>
      {!copilot && (
        <div className="sentinel-empty-action">
          <p>Briefing no generado para esta ventana.</p>
          <button className="primary" onClick={onGenerate} disabled={loading}>
            <ShieldCheck size={16} />
            {loading ? "Generando" : "Generar diagnóstico"}
          </button>
        </div>
      )}
      {copilot && (
        <div className="sentinel-copilot-body">
          <p className="sentinel-summary">{copilot.incident_summary}</p>
          <p className="sentinel-impact">{copilot.impact_description}</p>
          <div className="sentinel-action-list">
            {copilot.recommended_actions.map((action, index) => (
              <article className={`sentinel-action urgency-${action.urgency}`} key={`${action.order}-${action.action}`}>
                <div>
                  <strong>#{action.order} {action.action}</strong>
                  <span>{action.requires_approval ? "requiere aprobación" : "diagnóstico seguro"}</span>
                </div>
                {action.sql && (
                  <div className="sentinel-sql-block">
                    <button onClick={() => void copySql(action.sql ?? "", index)}>
                      {copied === index ? <CheckCircle2 size={15} /> : <Copy size={15} />}
                      {copied === index ? "Copiado" : "Copiar SQL"}
                    </button>
                    <pre>{action.sql}</pre>
                  </div>
                )}
              </article>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
