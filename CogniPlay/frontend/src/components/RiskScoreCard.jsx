import React from 'react';
import { motion } from 'framer-motion';
import { CONDITION, riskStyle, levelFor, INK } from './theme';

/**
 * Hero stat tile for one condition's risk score.
 *
 * The score is the headline, so it is rendered as a large number rather than a
 * chart. The meter beneath it is a magnitude encoding, not decoration.
 *
 * Accessibility: the risk level is carried by an icon AND a text label AND the
 * colour - never colour alone, which matters because a parent may be
 * colour-blind and this is the single most consequential number on the page.
 */
export default function RiskScoreCard({ condition, score, level, delay = 0 }) {
  const meta = CONDITION[condition] || { label: condition, color: INK.secondary };
  const resolved = level || levelFor(score);
  const status = riskStyle(resolved);
  const pct = Math.round((score ?? 0) * 100);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay }}
      className="bg-white rounded-2xl border border-slate-200 p-6 flex flex-col"
    >
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-2">
          {/* Small colour chip carries series identity; the text stays ink-coloured. */}
          <span
            className="w-3 h-3 rounded-full shrink-0"
            style={{ backgroundColor: meta.color }}
            aria-hidden="true"
          />
          <h3 className="font-bold text-slate-800">{meta.label}</h3>
        </div>

        <span
          className="px-2.5 py-1 rounded-full text-xs font-bold flex items-center gap-1.5 shrink-0"
          style={{ backgroundColor: status.bg, color: status.color }}
        >
          <span aria-hidden="true">{status.icon}</span>
          {resolved}
        </span>
      </div>

      <div className="flex items-baseline gap-1 mb-1">
        <span className="text-5xl font-extrabold tabular-nums" style={{ color: INK.primary }}>
          {pct}
        </span>
        <span className="text-xl font-bold text-slate-400">%</span>
      </div>
      <p className="text-sm mb-4" style={{ color: INK.secondary }}>
        {status.blurb}
      </p>

      {/* Magnitude meter. 4px rounded end anchored to the baseline. */}
      <div className="mt-auto">
        <div className="h-2.5 w-full rounded-full bg-slate-100 overflow-hidden">
          <motion.div
            className="h-full rounded-full"
            style={{ backgroundColor: status.color }}
            initial={{ width: 0 }}
            animate={{ width: `${pct}%` }}
            transition={{ duration: 0.8, delay: delay + 0.2, ease: 'easeOut' }}
          />
        </div>
        <div className="flex justify-between mt-1.5 text-[11px] font-medium text-slate-400">
          <span>Low</span>
          <span>Moderate</span>
          <span>High</span>
        </div>
      </div>
    </motion.div>
  );
}
