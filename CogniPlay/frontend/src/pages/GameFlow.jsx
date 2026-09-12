import React, { useState, useRef, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';

import LetterLand from '../games/LetterLand';
import NumberNinja from '../games/NumberNinja';
import ButterflyGame from '../games/ButterflyGame';
import ShapeTracer from '../games/ShapeTracer';

import ProgressBar from '../components/ProgressBar';
import LoadingScreen from '../components/LoadingScreen';
import { submitGame } from '../utils/api';
import { summariseGaze, clearBuffer } from '../utils/firebase';

/** Order matters - the payload keys are positional against this list. */
const SEQUENCE = [
  { key: 'letter_land', Component: LetterLand, title: 'Letter Land', icon: '🫧' },
  { key: 'number_ninja', Component: NumberNinja, title: 'Number Ninja', icon: '🥭' },
  { key: 'butterfly_game', Component: ButterflyGame, title: 'Butterfly Catcher', icon: '🦋' },
  { key: 'shape_tracer', Component: ShapeTracer, title: 'Shape Tracer', icon: '✏️' },
];

const STAGE = { INTRO: 'intro', PLAYING: 'playing', BREAK: 'break', ANALYSING: 'analysing', ERROR: 'error' };

export default function GameFlow() {
  const navigate = useNavigate();
  const location = useLocation();

  // A child can be handed in from a dashboard, or entered here for a walk-up demo.
  const passedChild = location.state?.child;
  const [child, setChild] = useState(
    passedChild || { id: 'demo-' + Date.now(), name: '', age: 5 }
  );

  const [stage, setStage] = useState(passedChild?.name ? STAGE.INTRO : 'who');
  const [index, setIndex] = useState(0);
  const [error, setError] = useState('');

  // Kept in a ref: games finish inside timers, and we must not read stale state.
  const collected = useRef({});
  const startedAt = useRef(null);

  const beginSession = () => {
    clearBuffer(child.id);
    collected.current = {};
    startedAt.current = Date.now();
    setIndex(0);
    setStage(STAGE.PLAYING);
  };

  const buildPayload = useCallback(() => {
    const g = collected.current;
    return {
      child_id: child.id,
      child_name: child.name,
      child_age: Number(child.age) || 5,
      session_date: new Date().toISOString(),
      total_duration_ms: Date.now() - (startedAt.current || Date.now()),
      letter_land: g.letter_land || {},
      number_ninja: g.number_ninja || {},
      butterfly_game: g.butterfly_game || {},
      shape_tracer: g.shape_tracer || {},
      eye_tracking: summariseGaze(child.id),
    };
  }, [child]);

  const runAnalysis = useCallback(async () => {
    setStage(STAGE.ANALYSING);
    setError('');
    try {
      const payload = buildPayload();
      const response = await submitGame(payload);
      navigate('/results', { state: { response, payload, child } });
    } catch (err) {
      console.error('[GameFlow] submit failed:', err);
      setError(
        err.response?.data?.error ||
          'We could not reach the CogniPlay server. Check that the backend is running on port 3001.'
      );
      setStage(STAGE.ERROR);
    }
  }, [buildPayload, navigate, child]);

  const handleGameComplete = useCallback(
    (gameData) => {
      const finished = SEQUENCE[index];
      collected.current[finished.key] = gameData || {};

      if (index + 1 >= SEQUENCE.length) {
        runAnalysis();
      } else {
        setStage(STAGE.BREAK);
        setTimeout(() => {
          setIndex((i) => i + 1);
          setStage(STAGE.PLAYING);
        }, 3000);
      }
    },
    [index, runAnalysis]
  );

  /* ------------------------------------------------------------- who is playing */
  if (stage === 'who') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-indigo-50 px-6">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (child.name.trim()) setStage(STAGE.INTRO);
          }}
          className="w-full max-w-sm bg-white rounded-2xl border border-slate-200 p-6 space-y-4"
        >
          <div className="text-center">
            <div className="text-5xl mb-2">👋</div>
            <h1 className="text-xl font-extrabold text-slate-900">Who&apos;s playing today?</h1>
          </div>

          <div>
            <label htmlFor="cname" className="block text-sm font-semibold text-slate-700 mb-1.5">
              Child&apos;s first name
            </label>
            <input
              id="cname"
              required
              value={child.name}
              onChange={(e) => setChild({ ...child, name: e.target.value })}
              className="w-full px-4 py-3 rounded-xl border border-slate-300 focus:border-indigo-500 outline-none"
            />
          </div>

          <div>
            <label htmlFor="cage" className="block text-sm font-semibold text-slate-700 mb-1.5">
              Age
            </label>
            <select
              id="cage"
              value={child.age}
              onChange={(e) => setChild({ ...child, age: Number(e.target.value) })}
              className="w-full px-4 py-3 rounded-xl border border-slate-300 outline-none"
            >
              {[4, 5, 6].map((a) => (
                <option key={a} value={a}>{a} years old</option>
              ))}
            </select>
          </div>

          <button className="w-full py-3 rounded-xl bg-indigo-600 text-white font-bold hover:bg-indigo-700">
            Continue
          </button>
        </form>
      </div>
    );
  }

  /* ------------------------------------------------------------------- intro */
  if (stage === STAGE.INTRO) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-b from-indigo-100 to-white px-6 py-12 no-select">
        <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="text-center">
          <div className="text-6xl mb-4">🎮</div>
          <h1 className="text-3xl md:text-4xl font-extrabold text-slate-900 mb-2">
            Hi {child.name}! Ready to play?
          </h1>
          <p className="text-slate-600 mb-8">Four quick games. About ten minutes.</p>
        </motion.div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-10 max-w-2xl w-full">
          {SEQUENCE.map((s, i) => (
            <motion.div
              key={s.key}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.12 }}
              className="bg-white rounded-2xl border border-slate-200 p-4 text-center"
            >
              <div className="text-4xl mb-2">{s.icon}</div>
              <p className="font-bold text-sm text-slate-700">{s.title}</p>
            </motion.div>
          ))}
        </div>

        <button
          onClick={beginSession}
          className="px-12 py-5 rounded-2xl bg-indigo-600 text-white font-extrabold text-2xl hover:bg-indigo-700 active:scale-95 transition-transform"
        >
          Let&apos;s Start! 🚀
        </button>

        <p className="text-xs text-slate-400 mt-6 max-w-md text-center">
          We may ask for camera access to see where {child.name} looks. It is optional -
          the games work fine without it, and no video is ever recorded or uploaded.
        </p>
      </div>
    );
  }

  /* ------------------------------------------------------------- between games */
  if (stage === STAGE.BREAK) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-green-50 no-select">
        <motion.div initial={{ scale: 0.5, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="text-center">
          <div className="text-7xl mb-4">⭐</div>
          <h2 className="text-3xl font-extrabold text-slate-900 mb-2">Great job, {child.name}!</h2>
          <p className="text-slate-600 mb-8">Next game starting...</p>
        </motion.div>
        <ProgressBar current={index + 1} total={SEQUENCE.length} />
      </div>
    );
  }

  /* ----------------------------------------------------------------- analysing */
  if (stage === STAGE.ANALYSING) {
    return <LoadingScreen />;
  }

  /* --------------------------------------------------------------------- error */
  if (stage === STAGE.ERROR) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-slate-50 px-6 text-center">
        <div className="text-6xl mb-4">😕</div>
        <h2 className="text-2xl font-extrabold text-slate-900 mb-2">Something went wrong</h2>
        <p className="text-slate-600 max-w-md mb-8">{error}</p>
        <div className="flex gap-3 flex-wrap justify-center">
          <button
            onClick={runAnalysis}
            className="px-6 py-3 rounded-xl bg-indigo-600 text-white font-bold hover:bg-indigo-700"
          >
            Try again
          </button>
          <button
            onClick={() => navigate('/')}
            className="px-6 py-3 rounded-xl bg-white border-2 border-slate-200 font-bold text-slate-700"
          >
            Back home
          </button>
        </div>
        <p className="text-xs text-slate-400 mt-6 max-w-sm">
          The gameplay data is still held in this browser tab - retrying will not
          make {child.name} play again.
        </p>
      </div>
    );
  }

  /* ------------------------------------------------------------------- playing */
  const { Component, key } = SEQUENCE[index];
  return (
    <div className="min-h-screen">
      <div className="fixed top-0 left-0 right-0 z-30 bg-white/80 backdrop-blur px-4 py-2">
        <ProgressBar current={index + 1} total={SEQUENCE.length} />
      </div>
      <AnimatePresence mode="wait">
        <motion.div key={key} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="pt-20">
          <Component childId={child.id} onComplete={handleGameComplete} />
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
