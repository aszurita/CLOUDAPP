import { Play, Terminal } from "lucide-react";
import { useState } from "react";

import type { FaultJob, FaultType } from "../../api/sentinel";
import { simulateSentinelFault } from "../../api/sentinel";
import { SeverityBadge } from "./SeverityBadge";

type Props = {
  faults: FaultType[];
  onJob: (job: FaultJob) => void;
};

export function FaultInjector({ faults, onJob }: Props) {
  const [faultType, setFaultType] = useState(faults[0]?.id ?? "lock_wait_storm");
  const [duration, setDuration] = useState(240);
  const [intensity, setIntensity] = useState("medium");
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    try {
      const job = await simulateSentinelFault(faultType, duration, intensity);
      onJob(job);
    } finally {
      setBusy(false);
    }
  }

  const selected = faults.find((fault) => fault.id === faultType);

  return (
    <section className="panel sentinel-fault-panel">
      <div className="panel-heading">
        <h2>Simulation Lab</h2>
        {selected && <SeverityBadge value={selected.risk} />}
      </div>
      <div className="sentinel-form-grid">
        <label>
          Fault
          <select value={faultType} onChange={(event) => setFaultType(event.target.value)}>
            {faults.map((fault) => (
              <option key={fault.id} value={fault.id}>{fault.title}</option>
            ))}
          </select>
        </label>
        <label>
          Duración
          <input type="number" min={30} max={900} value={duration} onChange={(event) => setDuration(Number(event.target.value))} />
        </label>
        <label>
          Intensidad
          <select value={intensity} onChange={(event) => setIntensity(event.target.value)}>
            <option value="low">low</option>
            <option value="medium">medium</option>
            <option value="high">high</option>
          </select>
        </label>
      </div>
      <button className="primary sentinel-run-btn" onClick={() => void run()} disabled={busy || faults.length === 0}>
        {selected?.has_lab_script ? <Terminal size={16} /> : <Play size={16} />}
        {busy ? "Preparando" : "Preparar dry-run"}
      </button>
    </section>
  );
}
