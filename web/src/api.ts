// לקוח HTTP דק לשרת המקומי. כל הבקשות נשלחות ל-/api (מוגש או מועבר דרך Vite proxy) ולא לאינטרנט.
import type {
  BenchmarkResponse, DashboardResponse, Draft, HoldingView, ImportResult, ProductType,
  SourceStatus, SyncResult, Track, WhatIfResponse,
} from "./types";

async function call<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data as { error?: string }).error ?? `שגיאה (${res.status})`);
  }
  return data as T;
}

export const api = {
  catalog: () => call<Track[]>("GET", "/catalog"),
  sources: () => call<SourceStatus[]>("GET", "/sources"),
  dashboard: (productType: ProductType) =>
    call<DashboardResponse>("GET", `/dashboard?product_type=${productType}`),
  holdings: (productType: ProductType) =>
    call<HoldingView[]>("GET", `/holdings?product_type=${productType}`),
  createHolding: (track_key: string, label: string, opened_on: string | null) =>
    call<{ holding_id: string }>("POST", "/holdings", { track_key, label, opened_on }),
  draftStatement: (holdingId: string, filename: string, contentBase64: string) =>
    call<Draft>("POST", `/holdings/${holdingId}/draft`, { filename, content_base64: contentBase64 }),
  confirmStatement: (holdingId: string, draft: Draft, edits: Record<string, unknown>) =>
    call<{ statement_id: string }>("POST", `/holdings/${holdingId}/confirm`, { draft, edits }),
  benchmark: (holdingId: string) => call<BenchmarkResponse>("GET", `/holdings/${holdingId}/benchmark`),
  whatif: (p: {
    holding_id: string; alt_track_key: string; window_months: number; horizon_years: number;
    fee_delta_pct: number; monthly_deposit_ils: number | null;
  }) => call<WhatIfResponse>("POST", "/whatif", p),
  importMarketCsv: (csv: string) => call<ImportResult>("POST", "/market/import", { csv }),
  syncSource: (source_id: string) => call<SyncResult>("POST", "/market/sync", { source_id }),
};

/** קריאת קובץ מהדפדפן ל-Base64 בלי לשלוח אותו לשום כתובת חיצונית. */
export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("לא ניתן לקרוא את הקובץ"));
    reader.onload = () => {
      const result = String(reader.result);
      resolve(result.slice(result.indexOf(",") + 1));
    };
    reader.readAsDataURL(file);
  });
}
