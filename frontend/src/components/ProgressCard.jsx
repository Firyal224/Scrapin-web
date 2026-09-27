import { useEffect, useState } from "react";

function useElapsed(active) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!active) return undefined;
    setSeconds(0);
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [active]);
  return seconds;
}

export default function ProgressCard({ job, onRetry }) {
  const running = job.status === "queued" || job.status === "running";
  const failed = job.status === "failed";
  const elapsed = useElapsed(running);
  const percent = job.total ? Math.round((job.done / job.total) * 100) : running ? 6 : 100;

  return (
    <div className={`progress-card ${failed ? "is-failed" : ""}`} aria-live="polite">
      <div className="progress-card__head">
        <span className="badge">{failed ? "❌ Gagal" : running ? "⏳ Scraping" : "✅ Selesai"}</span>
        <span className="muted small">
          “{job.keyword}” · {job.area} · maks {job.max_results}
          {job.price_min || job.price_max ? " · filter harga aktif" : null}
        </span>
      </div>

      <p className="progress-card__msg">{failed ? job.error : job.message}</p>

      {!failed && (
        <>
          <div className="bar">
            <div className={`bar__fill ${running ? "is-running" : ""}`} style={{ width: `${percent}%` }} />
          </div>
          <div className="progress-card__meta muted small">
            <span>{job.total ? `${job.done}/${job.total} tempat` : "Mencari kandidat..."}</span>
            {running && <span>{elapsed} detik</span>}
          </div>
        </>
      )}

      {failed && (
        <button type="button" className="btn btn--ghost" onClick={onRetry}>
          ↺ Coba lagi
        </button>
      )}
    </div>
  );
}
