import type { DashboardResponse } from "../types";
import { fmtIls, fmtPct } from "../format";

interface Props {
  data: DashboardResponse;
}

// מחלקות מלאות ולא מחרוזות דינמיות, כדי ש-Tailwind יכלול אותן בבנייה
const TONE: Record<string, string> = {
  slate: "text-slate-800",
  sky: "text-sky-700",
  emerald: "text-emerald-700",
  amber: "text-amber-700",
  rose: "text-rose-700",
};

function Card({ title, value, sub, tone = "slate" }: { title: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="text-xs font-medium text-slate-500">{title}</div>
      <div className={`mt-1 text-2xl font-bold ${TONE[tone]}`}>{value}</div>
      {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

export function Summary({ data }: Props) {
  const t = data.totals;
  const diff = t.estimated_ils - t.reported_ils;
  const scoreTone = data.health.score >= 80 ? "emerald" : data.health.score >= 60 ? "amber" : "rose";

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Card
          title="מדווחת (לפי דוח אחרון מאושר)"
          value={fmtIls(t.reported_ils)}
          sub="הסכום המאומת מהדוחות שאישרת"
        />
        <Card
          title="משוערכת להיום (הערכה)"
          value={fmtIls(t.estimated_ils)}
          sub={`טווח: ${fmtIls(t.estimated_low_ils)} עד ${fmtIls(t.estimated_high_ils)} · נתונים עד ${t.data_through ?? "—"}`}
          tone="sky"
        />
        <Card
          title="תשואה משוקללת מתחילת השנה"
          value={fmtPct(data.weighted_return_ytd_pct)}
          sub={`דמי ניהול מצבירה משוקללים: ${fmtPct(data.weighted_fee_accum_pct, 3)}`}
        />
        <Card
          title="ציון בריאות התיק (היוריסטיקה)"
          value={`${data.health.score}/100`}
          sub={`הפרש הערכה מול מדווח: ${fmtIls(diff)}`}
          tone={scoreTone}
        />
      </div>
      <details className="rounded-xl border border-slate-200 bg-white p-4 text-sm shadow-sm">
        <summary className="cursor-pointer font-medium text-slate-700">למה הציון הזה?</summary>
        <ul className="mt-2 list-disc space-y-1 pr-5 text-slate-600">
          {data.health.reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-slate-500">
          הציון הוא כלל אצבע שקוף לבדיקה עצמית, ולא המלצה להשקעה.
        </p>
      </details>
    </div>
  );
}
