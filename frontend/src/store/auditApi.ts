import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

export interface AuditSearchResultItem {
  payment_id: string;
  customer_id?: string;
  amount: number;
  failure_code?: string;
  recommended_action?: string;
  executed_action?: string;
  chosen_action?: string;
  expected_value: number;
  policy_allowed: boolean;
  policy_reason?: string;
  policy_outcome?: string;
  outcome?: string;
  recovered?: boolean;
  execution_result?: string;
  timestamp: string;
  bank?: string;
  payment_method?: string;
}

export interface AuditSearchAggregations {
  by_action: Record<string, number>;
  by_outcome: Record<string, number>;
}

export interface AuditSearchResponse {
  total: number;
  results: AuditSearchResultItem[];
  aggregations: AuditSearchAggregations;
  source: 'elasticsearch' | 'postgres' | 'in_memory' | string;
}

export interface AuditSearchParams {
  q?: string;
  failure_code?: string;
  action?: string;
  from?: string;
  to?: string;
  limit?: number;
  offset?: number;
}

export const auditApi = createApi({
  reducerPath: 'auditApi',
  baseQuery: fetchBaseQuery({
    baseUrl: (import.meta as any).env?.VITE_API_URL || 'http://localhost:8000',
  }),
  tagTypes: ['AuditSearch'],
  endpoints: (builder) => ({
    searchAudit: builder.query<AuditSearchResponse, AuditSearchParams>({
      query: (params) => {
        const queryParams = new URLSearchParams();
        if (params.q) queryParams.set('q', params.q);
        if (params.failure_code) queryParams.set('failure_code', params.failure_code);
        if (params.action) queryParams.set('action', params.action);
        if (params.from) queryParams.set('from', params.from);
        if (params.to) queryParams.set('to', params.to);
        if (params.limit !== undefined) queryParams.set('limit', String(params.limit));
        if (params.offset !== undefined) queryParams.set('offset', String(params.offset));
        return `/audit/search?${queryParams.toString()}`;
      },
      providesTags: ['AuditSearch'],
    }),
  }),
});

export const { useSearchAuditQuery } = auditApi;
