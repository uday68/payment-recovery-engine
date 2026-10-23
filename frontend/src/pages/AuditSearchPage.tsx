import React, { useState } from 'react';
import { useSearchAuditQuery } from '../store/auditApi';

export const AuditSearchPage: React.FC = () => {
  const [searchTerm, setSearchTerm] = useState('');
  const [failureCode, setFailureCode] = useState('');
  const [action, setAction] = useState('');

  // Active query state passed to RTK Query
  const [activeParams, setActiveParams] = useState({
    q: '',
    failure_code: '',
    action: '',
    limit: 50,
  });

  const { data, error, isLoading, isFetching, refetch } = useSearchAuditQuery(activeParams);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setActiveParams({
      q: searchTerm.trim(),
      failure_code: failureCode,
      action: action,
      limit: 50,
    });
  };

  const handleReset = () => {
    setSearchTerm('');
    setFailureCode('');
    setAction('');
    setActiveParams({
      q: '',
      failure_code: '',
      action: '',
      limit: 50,
    });
  };

  const getSourceBadge = (source?: string) => {
    if (source === 'elasticsearch') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          Elasticsearch Cluster
        </span>
      );
    }
    if (source === 'postgres') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-400 border border-blue-500/30">
          <span className="w-2 h-2 rounded-full bg-blue-400" />
          PostgreSQL ACID Fallback
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/30">
        <span className="w-2 h-2 rounded-full bg-amber-400" />
        In-Memory Audit Fallback
      </span>
    );
  };

  const getActionBadge = (act?: string) => {
    switch (act) {
      case 'RETRY_NOW':
        return <span className="px-2 py-0.5 rounded text-xs font-mono font-medium bg-cyan-500/20 text-cyan-300">RETRY_NOW</span>;
      case 'RETRY_LATER':
        return <span className="px-2 py-0.5 rounded text-xs font-mono font-medium bg-indigo-500/20 text-indigo-300">RETRY_LATER</span>;
      case 'SEND_REMINDER':
        return <span className="px-2 py-0.5 rounded text-xs font-mono font-medium bg-amber-500/20 text-amber-300">SEND_REMINDER</span>;
      default:
        return <span className="px-2 py-0.5 rounded text-xs font-mono font-medium bg-neutral-700 text-neutral-300">NO_ACTION</span>;
    }
  };

  const getOutcomeBadge = (outcome?: string) => {
    const norm = (outcome || '').toUpperCase();
    if (norm === 'RECOVERED') {
      return <span className="px-2 py-0.5 rounded text-xs font-semibold bg-emerald-500/20 text-emerald-300">RECOVERED</span>;
    }
    if (norm === 'FAILED') {
      return <span className="px-2 py-0.5 rounded text-xs font-semibold bg-rose-500/20 text-rose-300">FAILED</span>;
    }
    return <span className="px-2 py-0.5 rounded text-xs font-semibold bg-yellow-500/20 text-yellow-300">PENDING</span>;
  };

  return (
    <div className="w-full flex flex-col gap-6 pb-12 animate-fade-in text-gray-100">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-neutral-800 pb-5">
        <div>
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-2xl font-bold tracking-tight text-white">
              Decision Audit Search
            </h1>
            {getSourceBadge(data?.source)}
          </div>
          <p className="text-sm text-neutral-400 mt-1">
            Real-time indexed search across recovery decisions, expected values, policy guardrails, and execution outcomes.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="px-3.5 py-1.5 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-neutral-200 text-sm font-medium border border-neutral-700 transition"
          >
            {isFetching ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Filter & Search Form */}
      <form onSubmit={handleSearch} className="bg-neutral-900 border border-neutral-800 rounded-xl p-4 shadow-sm">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div className="md:col-span-2">
            <label className="block text-xs font-medium text-neutral-400 mb-1">Search Keywords</label>
            <input
              type="text"
              placeholder="Search payment ID, customer ID, or reason..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full px-3.5 py-2 rounded-lg bg-neutral-950 border border-neutral-700 text-sm text-neutral-100 placeholder-neutral-500 focus:outline-none focus:border-cyan-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-neutral-400 mb-1">Failure Code</label>
            <select
              value={failureCode}
              onChange={(e) => setFailureCode(e.target.value)}
              className="w-full px-3.5 py-2 rounded-lg bg-neutral-950 border border-neutral-700 text-sm text-neutral-100 focus:outline-none focus:border-cyan-500"
            >
              <option value="">All Failure Codes</option>
              <option value="BANK_TIMEOUT">BANK_TIMEOUT</option>
              <option value="NETWORK_ERROR">NETWORK_ERROR</option>
              <option value="LIMIT_EXCEEDED">LIMIT_EXCEEDED</option>
              <option value="INSUFFICIENT_FUNDS">INSUFFICIENT_FUNDS</option>
              <option value="CARD_EXPIRED">CARD_EXPIRED</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-neutral-400 mb-1">Action</label>
            <select
              value={action}
              onChange={(e) => setAction(e.target.value)}
              className="w-full px-3.5 py-2 rounded-lg bg-neutral-950 border border-neutral-700 text-sm text-neutral-100 focus:outline-none focus:border-cyan-500"
            >
              <option value="">All Actions</option>
              <option value="RETRY_NOW">RETRY_NOW</option>
              <option value="RETRY_LATER">RETRY_LATER</option>
              <option value="SEND_REMINDER">SEND_REMINDER</option>
              <option value="NO_ACTION">NO_ACTION</option>
            </select>
          </div>
        </div>
        <div className="flex items-center justify-end gap-2.5 mt-4 pt-3 border-t border-neutral-800">
          <button
            type="button"
            onClick={handleReset}
            className="px-4 py-1.5 rounded-lg text-sm text-neutral-400 hover:text-neutral-200 transition"
          >
            Clear Filters
          </button>
          <button
            type="submit"
            className="px-5 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-semibold shadow-sm transition"
          >
            Search Decisions
          </button>
        </div>
      </form>

      {/* Aggregation Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-4">
          <span className="text-xs font-medium text-neutral-400 uppercase tracking-wider">Total Matches</span>
          <div className="text-2xl font-bold text-white mt-1">
            {isLoading ? '...' : (data?.total ?? 0).toLocaleString()}
          </div>
          <p className="text-xs text-neutral-500 mt-1">Query filtered decisions</p>
        </div>

        <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-4">
          <span className="text-xs font-medium text-neutral-400 uppercase tracking-wider">Action Breakdown</span>
          <div className="flex flex-wrap gap-2 mt-2">
            {Object.entries(data?.aggregations?.by_action || {}).map(([actKey, count]) => (
              <span key={actKey} className="px-2 py-0.5 rounded text-xs bg-neutral-800 border border-neutral-700 text-neutral-300 font-mono">
                {actKey}: <strong className="text-white">{count}</strong>
              </span>
            ))}
            {(!data?.aggregations?.by_action || Object.keys(data.aggregations.by_action).length === 0) && (
              <span className="text-xs text-neutral-500">No action data</span>
            )}
          </div>
        </div>

        <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-4">
          <span className="text-xs font-medium text-neutral-400 uppercase tracking-wider">Outcome Breakdown</span>
          <div className="flex flex-wrap gap-2 mt-2">
            {Object.entries(data?.aggregations?.by_outcome || {}).map(([outKey, count]) => (
              <span key={outKey} className="px-2 py-0.5 rounded text-xs bg-neutral-800 border border-neutral-700 text-neutral-300 font-mono">
                {outKey}: <strong className="text-white">{count}</strong>
              </span>
            ))}
            {(!data?.aggregations?.by_outcome || Object.keys(data.aggregations.by_outcome).length === 0) && (
              <span className="text-xs text-neutral-500">No outcome data</span>
            )}
          </div>
        </div>
      </div>

      {/* Results Table */}
      <div className="bg-neutral-900 border border-neutral-800 rounded-xl overflow-hidden shadow-sm">
        <div className="p-4 border-b border-neutral-800 flex items-center justify-between">
          <h2 className="text-base font-semibold text-white">Decision Results</h2>
          <span className="text-xs text-neutral-400">Showing top {data?.results?.length ?? 0} hits</span>
        </div>

        {error && (
          <div className="p-6 text-center text-rose-400 text-sm">
            Error loading audit records. Please verify backend connection.
          </div>
        )}

        {isLoading ? (
          <div className="p-12 text-center text-neutral-400 text-sm">
            Searching audit index...
          </div>
        ) : (!data?.results || data.results.length === 0) ? (
          <div className="p-12 text-center text-neutral-500 text-sm">
            No decision audit records found matching the given filters.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-sm">
              <thead>
                <tr className="border-b border-neutral-800 bg-neutral-950/50 text-neutral-400 text-xs font-medium uppercase tracking-wider">
                  <th className="py-3 px-4">Payment ID</th>
                  <th className="py-3 px-4">Failure Code</th>
                  <th className="py-3 px-4">Chosen Action</th>
                  <th className="py-3 px-4">Expected Value</th>
                  <th className="py-3 px-4">Policy</th>
                  <th className="py-3 px-4">Execution Result</th>
                  <th className="py-3 px-4">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-800/60 font-sans">
                {data.results.map((row) => (
                  <tr key={row.payment_id} className="hover:bg-neutral-800/40 transition">
                    <td className="py-3 px-4 font-mono text-xs text-cyan-300">
                      {row.payment_id}
                    </td>
                    <td className="py-3 px-4 text-xs font-mono text-neutral-300">
                      {row.failure_code || '—'}
                    </td>
                    <td className="py-3 px-4">
                      {getActionBadge(row.chosen_action || row.executed_action || row.recommended_action)}
                    </td>
                    <td className="py-3 px-4 font-mono text-xs text-neutral-200">
                      ₹{row.expected_value.toFixed(2)}
                    </td>
                    <td className="py-3 px-4">
                      {row.policy_allowed ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-emerald-500/15 text-emerald-400">
                          ALLOWED
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-rose-500/15 text-rose-400" title={row.policy_reason || ''}>
                          BLOCKED
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4">
                      {getOutcomeBadge(row.execution_result || row.outcome)}
                    </td>
                    <td className="py-3 px-4 text-xs text-neutral-400 whitespace-nowrap">
                      {row.timestamp ? row.timestamp.replace('T', ' ').slice(0, 19) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default AuditSearchPage;
