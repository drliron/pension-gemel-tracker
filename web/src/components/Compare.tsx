import { useEffect, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import type { BenchmarkResponse, HoldingView, Track, WhatIfResponse } from "../types";
import { fmtIls, fmtPct } from "../format";

interface Props {
  holdings: HoldingView[];
  catalog: Track[];
}

export function Compare({ holdings, catalog }: Props) {
  const active = holdings.filter((h) => h.status === "active" && h.latest);
  const [holdingId, setHoldingId] = useState<string>(active[0]?.holding_id ?? "");
  const [bench, setBench] = useState<BenchmarkResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!holdingId) return;
    setError(null);
    api.benchmark(holdingId).then(setBench).catch((e: Error) => setError(e.message));
  }, [holdingId]);

  if (active.length === 0) {
    return <p className="text-sm text-slate-500">אין אחזקות פעילות עם דוח מאושר להשוואה.</p>;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm text-slate-700">
          אחזקה להשוואה:{" "}
          <select className="rounded-lg border border-slate-300 px-2 py-1.5"
            value={holdingId} onChange={(e) => setHoldingId(e.target.value)}>
            {active.map((h) => (
              <option key={h.holding_id} value={h.holding_id}>{h.label}</option>
            ))}
          </select>
        </label>
      </div>

      {error && <p className="text-sm text-rose-700">{error}</p>}
      {bench && (
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <h3 className="font-semibold text-slate-800">
            השוואה לקבוצה ({bench.summary.peer_count} מסלולים באותה קטגוריה)
          </h3>
          <p className="mb-3 text-sm text-slate-600">
            מיקום המסלול שלך לפי תשואה ב-12 חודשים: {bench.summary.own_rank ?? "—"} מתוך {bench.summary.peer_count}.
            חציון דמי ניהול מצבירה בקבוצה: {fmtPct(bench.summary.median_fee_accum_pct, 3)}.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-right text-sm">
              <thead className="border-b text-xs text-slate-500">
                <tr>
                  <th className="py-2">מסלול</th>
                  <th>תשואה 12 חודשים</th>
                  <th>תשואה שנתית 3 שנים</th>
                  <th>דמי ניהול מצבירה</th>
                  <th>דמי ניהול מהפקדות</th>
                  <th>שארפ 5 שנים</th>
                </tr>
              </thead>
              <tbody>
                {bench.rows.map((r) => (
                  <tr key={r.track_key} className={`border-b last:border-0 ${r.is_own ? "bg-emerald-50 font-semibold" : ""}`}>
                    <td className="py-2">{r.label}{r.is_own ? " (המסלול שלך)" : ""}</td>
                    <td>{fmtPct(r.return_12m_pct)}</td>
                    <td>{fmtPct(r.return_3y_annual_pct)}</td>
                    <td>{fmtPct(r.fee_accum_pct, 3)}</td>
                    <td>{fmtPct(r.fee_deposit_pct)}</td>
                    <td>{r.sharpe_5y?.toFixed(2) ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {holdingId && <WhatIf holdingId={holdingId} catalog={catalog} holdings={active} />}
    </div>
  );
}

function WhatIf({ holdingId, catalog, holdings }: { holdingId: string; catalog: Track[]; holdings: HoldingView[] }) {
  const holding = holdings.find((h) => h.holding_id === holdingId);
  const [alt, setAlt] = useState("");
  const [windowMonths, setWindowMonths] = useState(36);
  const [horizon, setHorizon] = useState(10);
  const [feeDelta, setFeeDelta] = useState(0);
  const [deposit, setDeposit] = useState<number | null>(null);
  const [result, setResult] = useState<WhatIfResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!alt) return;
    let cancelled = false;
    api
      .whatif({ holding_id: holdingId, alt_track_key: alt, window_months: windowMonths, horizon_years: horizon,
        fee_delta_pct: feeDelta, monthly_deposit_ils: deposit })
      .then((r) => {
        if (!cancelled) {
          setResult(r);
          setError(null);
        }
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [holdingId, alt, windowMonths, horizon, feeDelta, deposit]);

  const chartData = result
    ? result.current.map((p, i) => ({ year: p.year, current: p.value, alternative: result.alternative[i]?.value }))
    : [];

  return (
    <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="font-semibold text-slate-800">מה אם? סימולטור מסלולים</h3>
      <p className="text-xs text-slate-500">
        מבוסס על תשואות עבר בלבד, ואינו מבטיח תשואות עתידיות. מסלול נוכחי:{" "}
        {holding?.track_name ?? "—"}
      </p>

      <div className="grid gap-4 md:grid-cols-2">
        <label className="text-sm">
          מסלול חלופי
          <select className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5"
            value={alt} onChange={(e) => setAlt(e.target.value)}>
            <option value="">— בחר מסלול —</option>
            {catalog.filter((t) => t.track_key !== holding?.track_key).map((t) => (
              <option key={t.track_key} value={t.track_key}>{t.fund_name} · {t.track_name}</option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          חלון תשואה היסטורי: {windowMonths} חודשים
          <input type="range" min={12} max={60} step={12} value={windowMonths} className="w-full"
            onChange={(e) => setWindowMonths(Number(e.target.value))} />
        </label>
        <label className="text-sm">
          אופק: {horizon} שנים
          <input type="range" min={1} max={30} step={1} value={horizon} className="w-full"
            onChange={(e) => setHorizon(Number(e.target.value))} />
        </label>
        <label className="text-sm">
          שינוי בדמי ניהול מצבירה של החלופה: {feeDelta > 0 ? "+" : ""}{feeDelta.toFixed(2)}% בשנה
          <input type="range" min={-0.5} max={1} step={0.05} value={feeDelta} className="w-full"
            onChange={(e) => setFeeDelta(Number(e.target.value))} />
        </label>
        <label className="text-sm">
          הפקדה חודשית (₪)
          <input type="number" className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5"
            value={deposit ?? ""}
            placeholder="כמו בדוח האחרון"
            onChange={(e) => setDeposit(e.target.value === "" ? null : Number(e.target.value))} />
        </label>
      </div>

      {error && <p className="text-sm text-rose-700">{error}</p>}
      {result && (
        <>
          <p className="text-sm text-slate-700">
            בסוף {result.horizon_years} שנים, ההפרש בין החלופה ({result.alternative_label}) למסלול הנוכחי:{" "}
            <strong className={result.difference_at_horizon_ils >= 0 ? "text-emerald-700" : "text-rose-700"}>
              {fmtIls(result.difference_at_horizon_ils)}
            </strong>
          </p>
          <div className="h-72" dir="rtl">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="year" tick={{ fontSize: 11 }} label={{ value: "שנים", position: "insideBottom", offset: -4 }} />
                <YAxis tickFormatter={(v: number) => fmtIls(v)} tick={{ fontSize: 11 }} width={110} />
                <Tooltip formatter={(v: number) => fmtIls(v)} />
                <Legend />
                <Line type="monotone" dataKey="current" name="נוכחי" stroke="#0f766e" dot={false} strokeWidth={2} />
                <Line type="monotone" dataKey="alternative" name="חלופה" stroke="#7c3aed" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="text-xs text-slate-500">{result.note}</p>
        </>
      )}
    </div>
  );
}
