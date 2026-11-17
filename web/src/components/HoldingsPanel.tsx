import { useState } from "react";
import { api } from "../api";
import type { HoldingView, Track } from "../types";
import { fmtDate, fmtIls, fmtPeriod } from "../format";
import { TimelineChart } from "./TimelineChart";
import { StatementImport } from "./StatementImport";

interface Props {
  holdings: HoldingView[];
  catalog: Track[];
  onChanged: () => void;
}

export function HoldingsPanel({ holdings, catalog, onChanged }: Props) {
  const [selected, setSelected] = useState<string | null>(holdings[0]?.holding_id ?? null);
  const [newTrack, setNewTrack] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [error, setError] = useState<string | null>(null);

  const current = holdings.find((h) => h.holding_id === selected) ?? holdings[0];

  async function addHolding() {
    setError(null);
    try {
      const r = await api.createHolding(newTrack, newLabel, null);
      setNewTrack("");
      setNewLabel("");
      setSelected(r.holding_id);
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[18rem_1fr]">
      <aside className="space-y-3">
        <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
          <h3 className="mb-2 text-sm font-semibold text-slate-700">האחזקות שלי</h3>
          <ul className="space-y-1">
            {holdings.map((h) => (
              <li key={h.holding_id}>
                <button
                  type="button"
                  onClick={() => setSelected(h.holding_id)}
                  className={`w-full rounded-lg px-3 py-2 text-right text-sm ${
                    current?.holding_id === h.holding_id ? "bg-emerald-50 font-semibold text-emerald-800" : "hover:bg-slate-50"
                  } ${h.status === "closed" ? "opacity-60" : ""}`}
                >
                  <div>{h.label}</div>
                  <div className="text-xs text-slate-500">
                    {h.track_name} · {h.status === "closed" ? "נסגרה" : "פעילה"}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="space-y-2 rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-700">אחזקה חדשה</h3>
          <input className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm" placeholder="שם לתצוגה"
            value={newLabel} onChange={(e) => setNewLabel(e.target.value)} />
          <select className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm" value={newTrack}
            onChange={(e) => setNewTrack(e.target.value)}>
            <option value="">— בחר מסלול —</option>
            {catalog.map((t) => (
              <option key={t.track_key} value={t.track_key}>
                {t.fund_name} · {t.track_name}
              </option>
            ))}
          </select>
          <button type="button" disabled={!newTrack} onClick={addHolding}
            className="w-full rounded-lg bg-slate-800 px-3 py-1.5 text-sm text-white disabled:opacity-40">
            הוסף אחזקה
          </button>
          {error && <p className="text-xs text-rose-700">{error}</p>}
        </div>
      </aside>

      {current ? (
        <div className="space-y-4">
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <h2 className="text-lg font-semibold text-slate-800">{current.label}</h2>
            <p className="text-sm text-slate-600">{current.track_name}</p>
            {current.latest ? (
              <div className="mt-3 grid gap-3 md:grid-cols-3">
                <div>
                  <div className="text-xs text-slate-500">מדווחת ({fmtDate(current.latest.as_of)})</div>
                  <div className="font-bold">{fmtIls(current.latest.balance_ils)}</div>
                </div>
                {current.estimate && (
                  <>
                    <div>
                      <div className="text-xs text-slate-500">משוערכת להיום (הערכה)</div>
                      <div className="font-bold text-sky-700">{fmtIls(current.estimate.estimated_balance_ils)}</div>
                      <div className="text-xs text-slate-500">
                        טווח {fmtIls(current.estimate.low_ils)} עד {fmtIls(current.estimate.high_ils)} · נתונים עד{" "}
                        {fmtPeriod(current.estimate.data_through)}
                      </div>
                    </div>
                    <details className="text-xs text-slate-600">
                      <summary className="cursor-pointer">הנחות החישוב</summary>
                      <ul className="mt-1 list-disc pr-4">
                        {current.estimate.assumptions.map((a) => (
                          <li key={a}>{a}</li>
                        ))}
                      </ul>
                    </details>
                  </>
                )}
              </div>
            ) : (
              <p className="mt-3 text-sm text-slate-500">עדיין אין דוח מאושר לאחזקה הזו.</p>
            )}
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <h3 className="mb-2 font-semibold text-slate-800">ציר זמן וצבירה</h3>
            <TimelineChart holding={current} />
            {current.transitions.length > 0 && (
              <div className="mt-3">
                <h4 className="text-sm font-semibold text-slate-700">מעברי מסלול</h4>
                <ul className="mt-1 space-y-1 text-sm text-slate-700">
                  {current.transitions.map((t) => (
                    <li key={t.effective_on + t.to_track}>
                      <span className="font-medium">{fmtDate(t.effective_on)}</span>: מ-{t.from_track} ל-{t.to_track}
                      <span className="text-xs text-slate-500"> (מוערך לפי שני דוחות מאושרים)</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {current.status === "active" && (
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <h3 className="mb-2 font-semibold text-slate-800">הוספת דוח</h3>
              <StatementImport holdingId={current.holding_id} catalog={catalog} onConfirmed={onChanged} />
            </div>
          )}
        </div>
      ) : (
        <p className="text-sm text-slate-500">אין אחזקות עדיין. הוסף אחזקה כדי להתחיל.</p>
      )}
    </div>
  );
}
