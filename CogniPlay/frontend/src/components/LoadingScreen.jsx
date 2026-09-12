import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';

const DEFAULT_MESSAGES = [
  'Counting your clicks...',
  'Looking at your patterns...',
  'Watching how you traced...',
  'Almost ready...',
];

/**
 * Friendly waiting screen shown while the AI service analyses a session.
 * Rotates reassuring messages so a long wait never feels stuck.
 */
export default function LoadingScreen({
  title = 'Our AI is looking at your results...',
  messages = DEFAULT_MESSAGES,
  intervalMs = 2600,
}) {
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setIdx((i) => (i + 1) % messages.length), intervalMs);
    return () => clearInterval(t);
  }, [messages.length, intervalMs]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-b from-indigo-50 to-white p-6 no-select">
      <motion.div
        className="text-7xl mb-8"
        animate={{ rotate: [0, 10, -10, 0], scale: [1, 1.1, 1] }}
        transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
      >
        🧠
      </motion.div>

      <h2 className="text-2xl md:text-3xl font-extrabold text-slate-800 text-center mb-3">
        {title}
      </h2>

      <motion.p
        key={idx}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-lg text-slate-500 text-center h-7"
      >
        {messages[idx]}
      </motion.p>

      <div className="flex gap-2 mt-8">
        {[0, 1, 2].map((i) => (
          <motion.div
            key={i}
            className="w-3 h-3 rounded-full bg-indigo-400"
            animate={{ y: [0, -10, 0] }}
            transition={{ duration: 0.8, repeat: Infinity, delay: i * 0.15 }}
          />
        ))}
      </div>
    </div>
  );
}
