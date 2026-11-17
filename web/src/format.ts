const ils = new Intl.NumberFormat("he-IL", { style: "currency", currency: "ILS", maximumFractionDigits: 0 });
const num = new Intl.NumberFormat("he-IL", { maximumFractionDigits: 2 });
const dateFmt = new Intl.DateTimeFormat("he-IL", { year: "numeric", month: "short", day: "numeric" });

export const fmtIls = (v: number | null | undefined) => (v == null ? "—" : ils.format(v));

export const fmtPct = (v: number | null | undefined, digits = 2) =>
  v == null ? "—" : `${v.toLocaleString("he-IL", { maximumFractionDigits: digits })}%`;

export const fmtNum = (v: number | null | undefined) => (v == null ? "—" : num.format(v));

export const fmtDate = (iso: string | null | undefined) => {
  if (!iso) return "—";
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime()) ? iso : dateFmt.format(d);
};

/** תווית חודש קצרה מ-YYYY-MM, למשל "06/2026". */
export const fmtPeriod = (p: string | null | undefined) => (p ? `${p.slice(5, 7)}/${p.slice(0, 4)}` : "—");
