// טיפוסים שתואמים לתשובות השרת המקומי (worker/app/service.py).

export type ProductType = "all" | "pension" | "gemel_invest" | "hishtalmut" | "insurance_savings";

export interface Track {
  track_key: string;
  fund_name: string;
  track_name: string;
  product_type: Exclude<ProductType, "all">;
  age_group: "up_to_50" | "over_50" | "unknown";
  aliases: string[];
}

export interface Estimate {
  statement_id: string;
  base_balance_ils: number;
  estimated_balance_ils: number;
  low_ils: number;
  high_ils: number;
  data_through: string;
  method: string;
  assumptions: string[];
}

export interface TimelinePoint {
  as_of: string;
  balance_ils: number;
  track_key: string | null;
  track_name: string;
  fee_accum_pct: number | null;
}

export interface TransitionView {
  effective_on: string;
  from_track: string;
  to_track: string;
  evidence: string[];
  approximate: boolean;
}

export interface HoldingView {
  holding_id: string;
  label: string;
  status: "active" | "closed";
  track_key: string;
  track_name: string;
  product_type: Exclude<ProductType, "all">;
  age_group: string;
  opened_on: string | null;
  closed_on: string | null;
  latest: { as_of: string; balance_ils: number; fee_accum_pct: number | null } | null;
  estimate: Estimate | null;
  timeline: TimelinePoint[];
  transitions: TransitionView[];
}

export interface Allocation {
  total_ils: number;
  categories: { key: string; label: string; pct: number }[];
}

export interface DashboardResponse {
  product_type: ProductType;
  totals: {
    reported_ils: number;
    estimated_ils: number;
    estimated_low_ils: number;
    estimated_high_ils: number;
    data_through: string | null;
  };
  weighted_return_ytd_pct: number | null;
  weighted_fee_accum_pct: number | null;
  health: { score: number; reasons: string[] };
  allocation: Allocation;
  holdings: { holding_id: string; label: string; track_name: string; estimate: Estimate | null }[];
  data_status: SourceStatus[];
}

export interface SourceStatus {
  source_id: string;
  kind: string;
  latest_period: string | null;
  cache_status: string | null;
  fetched_at: string | null;
  automation_allowed: boolean;
  terms_reviewed_on: string | null;
}

export interface Draft {
  source_sha256: string;
  parser: { name: string; version: string } | null;
  confidence: number;
  warnings: string[];
  redactions: { id: number; account: number; name: number };
  clean_text: string;
  fields: {
    as_of?: string;
    balance_ils?: number;
    deposits_ytd_ils?: number;
    monthly_deposit_ils?: number;
    fee_deposit_pct?: number;
    fee_accum_pct?: number;
    reported_track_name?: string;
  };
  mapping: { track_key: string | null; method: string; candidates: string[] };
}

export interface BenchmarkRow {
  track_key: string;
  label: string;
  return_12m_pct: number | null;
  return_3y_annual_pct: number | null;
  fee_accum_pct: number | null;
  fee_deposit_pct: number | null;
  sharpe_5y: number | null;
  is_own: boolean;
}

export interface BenchmarkResponse {
  holding_id: string;
  label: string;
  rows: BenchmarkRow[];
  summary: {
    median_return_12m_pct: number | null;
    median_fee_accum_pct: number | null;
    own_rank: number | null;
    peer_count: number;
  };
}

export interface WhatIfResponse {
  horizon_years: number;
  window_months: number;
  current: { year: number; value: number }[];
  alternative: { year: number; value: number }[];
  difference_at_horizon_ils: number;
  current_label: string;
  alternative_label: string;
  note: string;
}

export interface SyncResult {
  status: string;
  message?: string;
  written?: number;
  unknown_tracks?: number;
}

export interface ImportResult {
  written: number;
  skipped: { row: number; reason: string }[];
}
