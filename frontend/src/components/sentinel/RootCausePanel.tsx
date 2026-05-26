import type { RootCause } from "../../api/sentinel";

type Props = {
  causes: RootCause[];
  active?: boolean;
  title?: string;
};

export function RootCausePanel({ causes, active = true, title = "RCA causa probable" }: Props) {
  return (
    <section className="panel sentinel-root-panel">
      <div className="panel-heading">
        <h2>{title}</h2>
        <span>{active ? causes.length : "en espera"}</span>
      </div>
      {!active && (
        <div className="sentinel-stable-state">
          <strong>Sin causa raíz activa</strong>
          <p>El predictor no detecta un incidente; las causas RCA se muestran cuando existe riesgo real.</p>
        </div>
      )}
      {active && (
      <div className="sentinel-cause-list">
        {causes.length === 0 && <p className="sentinel-muted">Sin causas rankeadas en esta ventana.</p>}
        {causes.map((cause) => (
          <article className="sentinel-cause" key={`${cause.rank}-${cause.cause}`}>
            <div className="sentinel-cause-head">
              <span>#{cause.rank}</span>
              <strong>{cause.cause.replace(/_/g, " ")}</strong>
              <em>{Math.round((cause.confidence ?? 0) * 100)}%</em>
            </div>
            <div className="sentinel-confidence">
              <i style={{ width: `${Math.round((cause.confidence ?? 0) * 100)}%` }} />
            </div>
            <div className="sentinel-evidence-mini">
              {(cause.evidence_features ?? []).slice(0, 4).map((item) => (
                <span key={item.feature}>
                  {item.feature}={Number(item.value ?? 0).toFixed(2)}
                </span>
              ))}
            </div>
          </article>
        ))}
      </div>
      )}
    </section>
  );
}
