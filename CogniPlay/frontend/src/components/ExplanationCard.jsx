import React from 'react';
import { CONDITION, INK } from './theme';

/**
 * "Why did the model say this?" panel for one condition.
 *
 * Renders the top contributing factors as a horizontal magnitude bar each.
 * Every bar is directly labelled with its plain-English description, so the
 * chart is readable without reference to a legend or a colour key.
 */
export default function ExplanationCard({ condition, explanation }) {
  const meta = CONDITION[condition] || { label: condition, color: INK.secondary };
  const factors = explanation?.top_factors || [];

  if (factors.length === 0) {
    return (
      <div className="bg-white rounded-2xl border border-slate-200 p-6">
        <h3 className="font-bold text-slate-800 mb-2">{meta.label}</h3>
        <p className="text-sm text-slate-500">
          Not enough gameplay data to explain this score.
        </p>
      </div>
    );
  }

  const maxContribution = Math.max(...factors.map((f) => Math.abs(f.contribution || 0)), 0.0001);

  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-6">
      <div className="flex items-center gap-2 mb-1">
        <span
          className="w-3 h-3 rounded-full shrink-0"
          style={{ backgroundColor: meta.color }}
          aria-hidden="true"
        />
        <h3 className="font-bold text-slate-800">Why we flagged {meta.label}</h3>
      </div>

      {explanation.summary && (
        <p className="text-sm mb-5 leading-relaxed" style={{ color: INK.secondary }}>
          {explanation.summary}
        </p>
      )}

      <ul className="space-y-4">
        {factors.map((f, i) => {
          const width = Math.round((Math.abs(f.contribution || 0) / maxContribution) * 100);
          return (
            <li key={f.feature || i}>
              <div className="flex items-baseline justify-between gap-3 mb-1.5">
                <span className="text-sm font-semibold text-slate-700">
                  {f.description || f.feature}
                </span>
                <span className="text-xs font-bold tabular-nums shrink-0" style={{ color: INK.secondary }}>
                  {Math.round((f.contribution || 0) * 100)}%
                </span>
              </div>
              <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{ width: `${width}%`, backgroundColor: meta.color }}
                />
              </div>
              {f.value != null && (
                <p className="text-xs text-slate-400 mt-1">
                  Observed: <span className="tabular-nums font-medium">{String(f.value)}</span>
                </p>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
