import { useState } from "react";
import { api } from "../api";
import type { ImportResult, SourceStatus } from "../types";
import { fmtPeriod } from "../format";

interface Props {
  sources: SourceStatus[];
  onChanged: () => void;
}

const SAMPLE = "track_key,period,monthly_return_pct,ytd_return_pct\n9201-02,2026-10,1.25,3.10";

export function MarketPanel({ sources, onChanged }: Props) {
  const [csv, setCsv] = useState(SAMPLE);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function importCsv() {
    setError(null);
    try {
      const r = await api.importMarketCsv(csv);
      setResult(r);
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function onFile(file: File) {
    setCsv(await file.text());
  }

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h3 className="mb-2 font-semibold text-slate-800">מקורות נתונים</h3>
        <table className="w-full text-right text-sm">
          <thead className="border-b text-xs text-slate-500">
            <tr>
              <th className="py-2">מקור</th>
              <th>סוג</th>
              <th>תקופה אחרונה</th>
              <th>מטמון</th>
              <th>שליפה אוטומטית</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((s) => (
              <tr key={s.source_id} className="border-b last:border-0">
                <td className="py-2">{s.source_id}</td>
                <td>{s.kind === "official_file" ? "רשמי" : "ידני"}</td>
                <td>{fmtPeriod(s.latest_period)}</td>
                <td>{s.cache_status ?? "—"}</td>
                <td>
                  {s.automation_allowed
                    ? s.terms_reviewed_on
                      ? `מותרת (תנאים נבדקו ${s.terms_reviewed_on})`
                      : "ממתינה לאישור תנאי שימוש"
                    : "כבויה"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-xs text-slate-500">
          שליפה אוטומטית מותרת רק לאחר שהוגדר URL וכאשר תנאי השימוש של המקור נבדקו. בלי זה המערכת לא פונה לאינטרנט.
        </p>
      </div>

      <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h3 className="font-semibold text-slate-800">ייבוא ידני (CSV) כגיבוי</h3>
        <p className="text-xs text-slate-500">
          עמודות: track_key, period (YYYY-MM), monthly_return_pct, וכן ytd_return_pct, return_12m_pct, return_3y_pct,
          return_5y_pct, sharpe_5y, fee_deposit_pct, fee_accum_pct, assets_ils_k. אפשר לטעון קובץ או להדביק.
        </p>
        <input type="file" accept=".csv,.txt" onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
          className="text-sm" />
        <textarea value={csv} onChange={(e) => setCsv(e.target.value)} rows={6}
          className="w-full rounded-lg border border-slate-300 p-2 font-mono text-xs" dir="ltr" />
        <button type="button" onClick={importCsv}
          className="rounded-lg bg-slate-800 px-4 py-2 text-sm text-white">
          ייבא
        </button>
        {error && <p className="text-sm text-rose-700">{error}</p>}
        {result && (
          <div className="text-sm">
            <p className="text-emerald-700">נכתבו {result.written} שורות.</p>
            {result.skipped.length > 0 && (
              <ul className="mt-1 list-disc pr-5 text-amber-700">
                {result.skipped.map((s) => (
                  <li key={s.row}>שורה {s.row + 1}: {s.reason}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
