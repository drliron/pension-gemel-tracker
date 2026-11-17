import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { DashboardResponse, HoldingView, ProductType, SourceStatus, Track } from "./types";
import { StatusBar } from "./components/StatusBar";
import { Summary } from "./components/Summary";
import { AllocationDonut } from "./components/AllocationDonut";
import { HoldingsPanel } from "./components/HoldingsPanel";
import { Compare } from "./components/Compare";
import { MarketPanel } from "./components/MarketPanel";
import { fmtIls, fmtPct } from "./format";

type Tab = "dashboard" | "holdings" | "compare" | "market";

const TABS: { id: Tab; label: string }[] = [
  { id: "dashboard", label: "דשבורד" },
  { id: "holdings", label: "אחזקות ודוחות" },
  { id: "compare", label: "השוואה ומה אם?" },
  { id: "market", label: "נתוני שוק" },
];

const FILTERS: { id: ProductType; label: string }[] = [
  { id: "all", label: "כל התיק" },
  { id: "pension", label: "פנסיה בלבד" },
  { id: "gemel_invest", label: "גמל להשקעה בלבד" },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [filter, setFilter] = useState<ProductType>("all");
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [holdings, setHoldings] = useState<HoldingView[]>([]);
  const [catalog, setCatalog] = useState<Track[]>([]);
  const [sources, setSources] = useState<SourceStatus[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [d, h, c, s] = await Promise.all([
        api.dashboard(filter),
        api.holdings("all"),
        api.catalog(),
        api.sources(),
      ]);
      setDashboard(d);
      setHoldings(h);
      setCatalog(c);
      setSources(s);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [filter]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div className="min-h-screen bg-slate-100 text-slate-800">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-4 px-4 py-3">
          <div>
            <h1 className="text-xl font-bold">ניהול תיק פנסיה וגמל</h1>
            <p className="text-xs text-slate-500">מקומי בלבד: הנתונים נשארים במחשב שלך</p>
          </div>
          <nav className="mr-auto flex gap-1 rounded-lg bg-slate-100 p-1">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                className={`rounded-md px-3 py-1.5 text-sm ${
                  tab === t.id ? "bg-white font-semibold shadow-sm" : "text-slate-600"
                }`}
              >
                {t.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-4 px-4 py-6">
        {error && (
          <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
            {error}. ודאו שהשרת המקומי פועל (python3 -m app.server בתיקיית worker).
          </div>
        )}

        <StatusBar sources={sources} dataThrough={dashboard?.totals.data_through ?? null} onRefresh={refresh} />

        {tab === "dashboard" && dashboard && (
          <>
            <div className="flex flex-wrap gap-2">
              {FILTERS.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => setFilter(f.id)}
                  className={`rounded-full border px-3 py-1 text-sm ${
                    filter === f.id ? "border-emerald-600 bg-emerald-600 text-white" : "border-slate-300 bg-white"
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <Summary data={dashboard} />
            <div className="grid gap-4 lg:grid-cols-[1fr_1.2fr]">
              <AllocationDonut allocation={dashboard.allocation} />
              <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <h3 className="mb-2 font-semibold text-slate-800">האחזקות בתיק</h3>
                <table className="w-full text-right text-sm">
                  <thead className="border-b text-xs text-slate-500">
                    <tr>
                      <th className="py-2">שם</th>
                      <th>מסלול</th>
                      <th>משוערכת</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dashboard.holdings.map((h) => (
                      <tr key={h.holding_id} className="border-b last:border-0">
                        <td className="py-2">{h.label}</td>
                        <td className="text-xs text-slate-600">{h.track_name}</td>
                        <td>{fmtIls(h.estimate?.estimated_balance_ils)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="mt-2 text-xs text-slate-500">
                  תשואה משוקללת מתחילת השנה: {fmtPct(dashboard.weighted_return_ytd_pct)}
                </p>
              </div>
            </div>
          </>
        )}

        {tab === "holdings" && <HoldingsPanel holdings={holdings} catalog={catalog} onChanged={refresh} />}
        {tab === "compare" && <Compare holdings={holdings} catalog={catalog} />}
        {tab === "market" && <MarketPanel sources={sources} onChanged={refresh} />}
      </main>
    </div>
  );
}
