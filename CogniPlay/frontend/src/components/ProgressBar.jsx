import React from 'react';
import { motion } from 'framer-motion';

/**
 * "Game 2 of 4" progress indicator shown between games.
 * Uses dots rather than a bare bar - 5-year-olds read countable dots better.
 */
export default function ProgressBar({ current, total = 4, label }) {
  const pct = Math.round((current / total) * 100);

  return (
    <div className="w-full max-w-md mx-auto no-select">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-semibold text-slate-600">
          {label || `Game ${current} of ${total}`}
        </span>
        <span className="text-sm font-semibold text-slate-500">{pct}%</span>
      </div>

      <div
        className="h-4 w-full rounded-full bg-slate-200 overflow-hidden"
        role="progressbar"
        aria-valuenow={current}
        aria-valuemin={0}
        aria-valuemax={total}
      >
        <motion.div
          className="h-full rounded-full bg-indigo-500"
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
        />
      </div>

      <div className="flex justify-center gap-3 mt-3">
        {Array.from({ length: total }).map((_, i) => (
          <div
            key={i}
            className={`w-4 h-4 rounded-full transition-colors ${
              i < current ? 'bg-indigo-500' : 'bg-slate-300'
            }`}
          />
        ))}
      </div>
    </div>
  );
}
