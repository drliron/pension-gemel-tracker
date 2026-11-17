import { useState } from "react";
import { api, fileToBase64 } from "../api";
import type { Draft, Track } from "../types";
import { fmtPct } from "../format";

interface Props {
  holdingId: string;
  catalog: Track[];
  onConfirmed: () => void;
}

type Edits = Partial<{
  as_of: string;
  balance_ils: number;
  monthly_deposit_ils: number;
  fee_deposit_pct: number;
  fee_accum_pct: number;
  matched_track_key: string;
}>;

/**
 * ייבוא דוח: שלב טיוטה (השרת מוחק מזהים ומחזיר טקסט נקי לתצוגה) -> עריכה ואישור משתמש -> שמירה.
 * שום דבר לא נשמר לפני לחיצה על "אשר ושמור".
 */
export function StatementImport({ holdingId, catalog, onConfirmed }: Props) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [edits, setEdits] = useState<Edits>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onFile(file: File) {
    setError(null);
    setBusy(true);
    try {
      const b64 = await fileToBase64(file);
      setDraft(await api.draftStatement(holdingId, file.name, b64));
      setEdits({});
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!draft) {
    return (
      <div className="space-y-2">
        <label className="block rounded-xl border-2 border-dashed border-slate-300 bg-slate-50 p-6 text-center text-sm text-slate-600 hover:border-emerald-500">
          <input
            type="file"
            accept=".pdf,.csv,.txt"
            className="hidden"
            disabled={busy}
            onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
          />
          {busy ? "מעבד..." : "בחר קובץ דוח (PDF, CSV או TXT). הנתונים נבדקים מקומית לפני שמירה"}
        </label>
        {error && <p className="text-sm text-rose-700">{error}</p>}
      </div>
    );
  }

  const f = { ...draft.fields, ...edits };
  const trackKey = edits.matched_track_key ?? draft.mapping.track_key ?? "";
  const canConfirm = Boolean(f.as_of && f.balance_ils != null && trackKey);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      await api.confirmStatement(holdingId, draft!, { ...edits, matched_track_key: trackKey });
      setDraft(null);
      onConfirmed();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const input = "w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm";

  return (
    <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap gap-3 text-xs text-slate-600">
        <span>זיהוי תבנית: {draft.parser ? `${draft.parser.name} v${draft.parser.version}` : "לא זוהתה"}</span>
        <span>ביטחון החילוץ: {fmtPct(draft.confidence * 100, 0)}</span>
        <span>
          נמחקו מהטקסט: ת.ז. {draft.redactions.id} · חשבונות {draft.redactions.account} · שמות {draft.redactions.name}
        </span>
      </div>
      {draft.warnings.map((w) => (
        <p key={w} className="text-sm text-amber-700">
          {w}
        </p>
      ))}

      <div className="grid gap-3 md:grid-cols-2">
        <label className="text-sm">
          תאריך דוח
          <input className={input} type="date" value={f.as_of ?? ""}
            onChange={(e) => setEdits({ ...edits, as_of: e.target.value })} />
        </label>
        <label className="text-sm">
          יתרה (₪)
          <input className={input} type="number" step="0.01" value={f.balance_ils ?? ""}
            onChange={(e) => setEdits({ ...edits, balance_ils: Number(e.target.value) })} />
        </label>
        <label className="text-sm md:col-span-2">
          מסלול (לפי הדוח: {draft.fields.reported_track_name || "לא נמצא"})
          <select className={input} value={trackKey}
            onChange={(e) => setEdits({ ...edits, matched_track_key: e.target.value })}>
            <option value="">— בחר מסלול מהקטלוג —</option>
            {catalog.map((t) => (
              <option key={t.track_key} value={t.track_key}>
                {t.fund_name} · {t.track_name}
              </option>
            ))}
          </select>
          {draft.mapping.method === "ambiguous" && (
            <span className="text-xs text-amber-700">שם המסלול משותף לכמה קופות. יש לבחור ידנית.</span>
          )}
        </label>
        <label className="text-sm">
          הפקדה חודשית (₪)
          <input className={input} type="number" step="0.01" value={f.monthly_deposit_ils ?? ""}
            onChange={(e) => setEdits({ ...edits, monthly_deposit_ils: Number(e.target.value) })} />
        </label>
        <label className="text-sm">
          דמי ניהול מהפקדות (%)
          <input className={input} type="number" step="0.01" value={f.fee_deposit_pct ?? ""}
            onChange={(e) => setEdits({ ...edits, fee_deposit_pct: Number(e.target.value) })} />
        </label>
        <label className="text-sm">
          דמי ניהול מצבירה (%)
          <input className={input} type="number" step="0.01" value={f.fee_accum_pct ?? ""}
            onChange={(e) => setEdits({ ...edits, fee_accum_pct: Number(e.target.value) })} />
        </label>
      </div>

      <details className="text-sm">
        <summary className="cursor-pointer text-slate-700">תצוגת טקסט נקי (לבדיקה לפני אישור)</summary>
        <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-xs text-slate-700">
          {draft.clean_text}
        </pre>
      </details>

      {error && <p className="text-sm text-rose-700">{error}</p>}
      <div className="flex gap-2">
        <button type="button" disabled={!canConfirm || busy} onClick={confirm}
          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-40">
          אשר ושמור
        </button>
        <button type="button" onClick={() => setDraft(null)}
          className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700">
          ביטול
        </button>
      </div>
      <p className="text-xs text-slate-500">
        הנתונים נשמרים מקומית בלבד. רק אחרי אישור הדוח נכנס לחישובים ולציר הזמן.
      </p>
    </div>
  );
}
