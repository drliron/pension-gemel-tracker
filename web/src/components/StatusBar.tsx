import { useState } from "react";
import { api } from "../api";
import type { SourceStatus } from "../types";
import { fmtPeriod } from "../format";

interface Props {
  sources: SourceStatus[];
  dataThrough: string | null;
  onRefresh: () => void;
}

const OFFICIAL = "gemelnet_official";

export function StatusBar({ sources, dataThrough, onRefresh }: Props) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const official = sources.find((s) => s.source_id === OFFICIAL);

  async function sync() {
    setBusy(true);
    setMessage(null);
    try {
      const r = await api.syncSource(OFFICIAL);
      setMessage(r.message ?? (r.status === "ok" ? `עודכנו ${r.written} נתונים` : "הסנכרון הסתיים"));
      onRefresh();
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm shadow-sm">
      <span className="font-semibold text-slate-700">סטטוס נתוני שוק:</span>
      <span className="text-slate-600">
        נתונים עד <strong>{fmtPeriod(dataThrough)}</strong>
      </span>
      {official && (
        <span className="text-slate-500">
          מקור רשמי: {official.cache_status ?? "אין מטמון"}
          {official.fetched_at ? ` · נשלף ${official.fetched_at.slice(0, 16).replace("T", " ")}` : ""}
        </span>
      )}
      <button
        type="button"
        onClick={sync}
        disabled={busy}
        className="mr-auto rounded-lg bg-emerald-600 px-3 py-1.5 font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
      >
        {busy ? "מסנכרן..." : "סנכרן נתוני שוק עכשיו"}
      </button>
      {message && <span className="w-full text-amber-700">{message}</span>}
    </div>
  );
}
