import React from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { isLoggedIn, getCurrentUser } from '../utils/api';

const GAMES = [
  { icon: '🫧', name: 'Letter Land', blurb: 'Popping bubbles reveals letter reversals like b/d.' },
  { icon: '🥭', name: 'Number Ninja', blurb: 'Counting mangoes shows how number sense is developing.' },
  { icon: '🦋', name: 'Butterfly Catcher', blurb: 'Catching only blue butterflies measures sustained focus.' },
  { icon: '✏️', name: 'Shape Tracer', blurb: 'Tracing shapes captures fine motor control.' },
];

export default function Home() {
  const user = getCurrentUser();

  return (
    <div className="min-h-screen bg-gradient-to-b from-indigo-50 via-white to-white">
      <section className="max-w-5xl mx-auto px-6 pt-16 pb-12 text-center">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <div className="text-6xl mb-4">🧩</div>
          <h1 className="text-4xl md:text-5xl font-extrabold text-slate-900 mb-3">CogniPlay</h1>
          <p className="text-xl text-indigo-600 font-bold mb-6">
            Detect Early. Intervene Early. Change Lives.
          </p>
          <p className="text-lg text-slate-600 max-w-2xl mx-auto mb-8 leading-relaxed">
            A ten-minute game that helps spot early signs of dyslexia, dyscalculia
            and attention difficulties in 4-5 year olds - so support can start years
            earlier than it usually does.
          </p>

          <div className="flex flex-wrap gap-3 justify-center">
            <Link
              to={isLoggedIn() ? '/play' : '/register'}
              className="px-8 py-4 rounded-2xl bg-indigo-600 text-white font-bold text-lg hover:bg-indigo-700 transition-colors"
            >
              {isLoggedIn() ? "Let's Play! 🎮" : 'Get Started'}
            </Link>
            {isLoggedIn() && (
              <Link
                to={user?.role === 'teacher' ? '/teacher' : '/parent'}
                className="px-8 py-4 rounded-2xl bg-white border-2 border-slate-200 text-slate-700 font-bold text-lg hover:border-indigo-300 transition-colors"
              >
                View Dashboard
              </Link>
            )}
          </div>
        </motion.div>
      </section>

      <section className="max-w-5xl mx-auto px-6 pb-12">
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {GAMES.map((g, i) => (
            <motion.div
              key={g.name}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 * i, duration: 0.4 }}
              className="bg-white rounded-2xl border border-slate-200 p-5"
            >
              <div className="text-4xl mb-3">{g.icon}</div>
              <h3 className="font-bold text-slate-800 mb-1">{g.name}</h3>
              <p className="text-sm text-slate-500 leading-relaxed">{g.blurb}</p>
            </motion.div>
          ))}
        </div>
      </section>

      <section className="max-w-3xl mx-auto px-6 pb-20">
        <div className="rounded-2xl bg-amber-50 border border-amber-200 p-6">
          <h3 className="font-bold text-amber-900 mb-2 flex items-center gap-2">
            <span aria-hidden="true">▲</span> Please read this first
          </h3>
          <p className="text-sm text-amber-900 leading-relaxed">
            CogniPlay is a <strong>screening aid, not a diagnosis</strong>. It cannot
            tell you whether a child has a learning disability. A high score means
            &quot;worth showing to a professional&quot; - nothing more. Only a qualified
            clinician can diagnose dyslexia, dyscalculia or ADHD. Please do not make
            decisions about a child&apos;s education based on this result alone.
          </p>
        </div>
      </section>
    </div>
  );
}
