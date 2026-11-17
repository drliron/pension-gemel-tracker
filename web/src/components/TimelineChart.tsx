import {
  Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { HoldingView } from "../types";
import { fmtDate, fmtIls, fmtPeriod } from "../format";

/** גרף צבירה לאחזקה אחת. קווים אנכיים מסמנים מעברי מסלול (Transition) על ציר הזמן. */
export function TimelineChart({ holding }: { holding: HoldingView }) {
  const points = holding.timeline.map((p) => ({ date: p.as_of, balance: p.balance_ils, track: p.track_name }));
  if (holding.estimate) {
    points.push({
      date: holding.estimate.data_through, // נקודת הערכה נשארת ברמת חודש ולא מומצא יום
      balance: holding.estimate.estimated_balance_ils,
      track: "הערכה (ללא אישור)",
    });
  }

  if (points.length === 0) {
    return <p className="text-sm text-slate-500">אין דוחות מאושרים לאחזקה זו.</p>;
  }

  return (
    <div className="h-72" dir="rtl">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points} margin={{ top: 24, right: 16, left: 8, bottom: 8 }}>
          <defs>
            <linearGradient id="bal" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#0f766e" stopOpacity={0.35} />
              <stop offset="95%" stopColor="#0f766e" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="date" tickFormatter={(d: string) => (d.length === 10 ? fmtDate(d) : fmtPeriod(d))} tick={{ fontSize: 11 }} />
          <YAxis tickFormatter={(v: number) => fmtIls(v)} tick={{ fontSize: 11 }} width={110} />
          <Tooltip
            labelFormatter={(d) => (String(d).length === 10 ? fmtDate(String(d)) : fmtPeriod(String(d)))}
            formatter={(v: number, _n, item) => [fmtIls(v), String(item?.payload?.track ?? "")]}
          />
          {holding.transitions.map((t) => (
            <ReferenceLine
              key={t.effective_on}
              x={t.effective_on}
              stroke="#d97706"
              strokeDasharray="4 4"
              label={{ value: "מעבר מסלול", position: "top", fill: "#b45309", fontSize: 11 }}
            />
          ))}
          <Area type="monotone" dataKey="balance" stroke="#0f766e" fill="url(#bal)" strokeWidth={2} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
