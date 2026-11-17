import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { Allocation } from "../types";
import { fmtPct } from "../format";

// פלטה קבועה וניגודית, בלי צבעי מותג
const COLORS = ["#0f766e", "#2563eb", "#7c3aed", "#d97706", "#64748b"];

export function AllocationDonut({ allocation }: { allocation: Allocation }) {
  const data = allocation.categories.filter((c) => c.pct > 0);
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="mb-2 font-semibold text-slate-800">חשיפה משוקללת לאפיקים</h3>
      {data.length === 0 ? (
        <p className="text-sm text-slate-500">אין מספיק נתונים להרכב נכסים.</p>
      ) : (
        <div className="h-64" dir="rtl">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={data} dataKey="pct" nameKey="label" innerRadius="55%" outerRadius="85%" paddingAngle={2}>
                {data.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(v: number) => fmtPct(v, 1)} />
              <Legend verticalAlign="bottom" />
            </PieChart>
          </ResponsiveContainer>
        </div>
      )}
      <p className="mt-2 text-xs text-slate-500">
        משוקלל לפי יתרה משוערכת. הרכב הנכסים לפי המסלול האחרון שנטען.
      </p>
    </div>
  );
}
