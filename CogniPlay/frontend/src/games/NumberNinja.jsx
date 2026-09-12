import React, { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { logGameEvent } from '../utils/firebase';
import { initEyeTracking, stopEyeTracking, getGazeData } from '../utils/eyeTracking';

const GAME_KEY = 'number_ninja';
const TOTAL_ROUNDS = 20;
const ROUND_TIME_LIMIT_MS = 8000;

function getDifficultyRange(roundNumber) {
  if (roundNumber <= 7) return { min: 1, max: 5, level: 1 };
  if (roundNumber <= 14) return { min: 1, max: 7, level: 2 };
  return { min: 1, max: 10, level: 3 };
}

function randomMangoCount(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

const MANGO_POSITIONS = Array.from({ length: 10 }, (_, i) => ({
  top: 15 + (i % 5) * 14 + (Math.random() * 4 - 2),
  left: 12 + Math.floor(i / 5) * 40 + (Math.random() * 8 - 4),
}));

export default function NumberNinja({ childId, onComplete }) {
  const [round, setRound] = useState(1);
  const [score, setScore] = useState(0);
  const [mangoCount, setMangoCount] = useState(() => randomMangoCount(1, 5));
  const [visibleMangoes, setVisibleMangoes] = useState(0);
  const [selected, setSelected] = useState(null);
  const [feedback, setFeedback] = useState(null); // 'correct' | 'wrong' | null
  const [treeShake, setTreeShake] = useState(false);
  const [finished, setFinished] = useState(false);
  const [timeLeftMs, setTimeLeftMs] = useState(ROUND_TIME_LIMIT_MS);

  const roundStartRef = useRef(Date.now());
  const finishedRef = useRef(false);
  const roundTimeoutRef = useRef(null);
  const staggerTimeoutsRef = useRef([]);
  const tickIntervalRef = useRef(null);
  const answeredRef = useRef(false);

  const statsRef = useRef({
    total_rounds: 0,
    correct_answers: 0,
    wrong_answers: 0,
    response_times: [],
    number_errors: [],
    subitize_1_5: { correct: 0, total: 0 },
    subitize_6_10: { correct: 0, total: 0 },
  });

  useEffect(() => {
    (async () => {
      try {
        await initEyeTracking(childId, GAME_KEY);
      } catch (e) {
        // swallow
      }
    })();
    return () => {
      try {
        stopEyeTracking();
      } catch (e) {
        // swallow
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const clearAllTimers = useCallback(() => {
    if (roundTimeoutRef.current) clearTimeout(roundTimeoutRef.current);
    if (tickIntervalRef.current) clearInterval(tickIntervalRef.current);
    staggerTimeoutsRef.current.forEach((t) => clearTimeout(t));
    staggerTimeoutsRef.current = [];
  }, []);

  useEffect(() => {
    return () => clearAllTimers();
  }, [clearAllTimers]);

  const finishGame = useCallback(() => {
    if (finishedRef.current) return;
    finishedRef.current = true;
    clearAllTimers();
    setFinished(true);

    const s = statsRef.current;
    const accuracy = s.total_rounds > 0 ? s.correct_answers / s.total_rounds : 0;
    const avg_response_time_ms =
      s.response_times.length > 0
        ? s.response_times.reduce((a, b) => a + b, 0) / s.response_times.length
        : 0;
    const subitizing_accuracy_1_5 =
      s.subitize_1_5.total > 0 ? s.subitize_1_5.correct / s.subitize_1_5.total : 0;
    const subitizing_accuracy_6_10 =
      s.subitize_6_10.total > 0 ? s.subitize_6_10.correct / s.subitize_6_10.total : 0;

    const payload = {
      total_rounds: s.total_rounds,
      correct_answers: s.correct_answers,
      wrong_answers: s.wrong_answers,
      accuracy,
      avg_response_time_ms,
      number_errors: s.number_errors,
      subitizing_accuracy_1_5,
      subitizing_accuracy_6_10,
    };

    setTimeout(() => {
      if (typeof onComplete === 'function') {
        onComplete(payload);
      }
    }, 1500);
  }, [clearAllTimers, onComplete]);

  const startRound = useCallback(
    (roundNumber) => {
      clearAllTimers();
      answeredRef.current = false;
      const { min, max } = getDifficultyRange(roundNumber);
      const count = randomMangoCount(min, max);
      setMangoCount(count);
      setVisibleMangoes(0);
      setSelected(null);
      setFeedback(null);
      setTimeLeftMs(ROUND_TIME_LIMIT_MS);
      roundStartRef.current = Date.now();

      for (let i = 1; i <= count; i++) {
        const t = setTimeout(() => {
          setVisibleMangoes((prev) => Math.max(prev, i));
        }, i * 220);
        staggerTimeoutsRef.current.push(t);
      }

      tickIntervalRef.current = setInterval(() => {
        setTimeLeftMs((prev) => Math.max(0, prev - 200));
      }, 200);

      roundTimeoutRef.current = setTimeout(() => {
        handleAnswer(null, roundNumber, count);
      }, ROUND_TIME_LIMIT_MS);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [clearAllTimers]
  );

  useEffect(() => {
    startRound(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleAnswer = useCallback(
    (numberSelected, roundNumberOverride, mangoCountOverride) => {
      if (finishedRef.current || answeredRef.current) return;
      answeredRef.current = true;
      if (roundTimeoutRef.current) clearTimeout(roundTimeoutRef.current);
      if (tickIntervalRef.current) clearInterval(tickIntervalRef.current);

      const roundNumber = roundNumberOverride || round;
      const shownCount = mangoCountOverride !== undefined ? mangoCountOverride : mangoCount;
      const responseTimeMs = Date.now() - roundStartRef.current;
      const isCorrect = numberSelected === shownCount;
      const { level } = getDifficultyRange(roundNumber);

      const s = statsRef.current;
      s.total_rounds += 1;
      s.response_times.push(responseTimeMs);
      if (isCorrect) {
        s.correct_answers += 1;
      } else {
        s.wrong_answers += 1;
        s.number_errors.push({
          shown: shownCount,
          answered: numberSelected,
          time_ms: responseTimeMs,
        });
      }

      const bucket = shownCount <= 5 ? s.subitize_1_5 : s.subitize_6_10;
      bucket.total += 1;
      if (isCorrect) bucket.correct += 1;

      let gaze = { x: null, y: null };
      try {
        gaze = getGazeData() || { x: null, y: null };
      } catch (e) {
        gaze = { x: null, y: null };
      }

      logGameEvent(childId, GAME_KEY, {
        type: 'number_answer',
        mangoes_shown: shownCount,
        number_selected: numberSelected,
        is_correct: isCorrect,
        response_time_ms: responseTimeMs,
        round_number: roundNumber,
        difficulty_level: level,
        gaze_x: gaze.x,
        gaze_y: gaze.y,
      });

      setSelected(numberSelected);
      setFeedback(isCorrect ? 'correct' : 'wrong');
      if (isCorrect) {
        setScore((prev) => prev + 1);
        setTreeShake(true);
        setTimeout(() => setTreeShake(false), 600);
      }

      setTimeout(() => {
        if (roundNumber >= TOTAL_ROUNDS) {
          finishGame();
        } else {
          const nextRound = roundNumber + 1;
          setRound(nextRound);
          startRound(nextRound);
        }
      }, 1400);
    },
    [childId, round, mangoCount, finishGame, startRound]
  );

  if (finished) {
    return (
      <div className="w-full h-full min-h-[600px] flex flex-col items-center justify-center bg-green-100 rounded-3xl">
        <motion.div
          initial={{ scale: 0.5, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: 'spring', duration: 0.6 }}
          className="text-center"
        >
          <div className="text-7xl mb-4">Great Job! 🌟</div>
          <div className="text-3xl font-bold text-green-800">Score: {score} / {TOTAL_ROUNDS}</div>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="relative w-full h-full min-h-[600px] overflow-hidden rounded-3xl bg-gradient-to-b from-green-200 to-green-100">
      <div className="absolute top-4 left-4 z-20 bg-white/80 rounded-2xl px-5 py-2 shadow-lg">
        <span className="text-xl font-extrabold text-green-800">Score: {score}</span>
      </div>
      <div className="absolute top-4 right-4 z-20 bg-white/80 rounded-2xl px-5 py-2 shadow-lg">
        <span className="text-xl font-extrabold text-green-800">Round {round}/{TOTAL_ROUNDS}</span>
      </div>

      <div className="absolute top-20 left-0 right-0 z-20 flex justify-center">
        <div className="bg-yellow-200 rounded-3xl px-8 py-3 shadow-xl">
          <h1 className="text-xl md:text-2xl font-extrabold text-center text-green-900">
            How many mangoes do you see? 🥭
          </h1>
        </div>
      </div>

      <div className="absolute top-32 right-6 z-20 w-32 bg-white/60 rounded-full h-3 overflow-hidden">
        <motion.div
          className="h-full bg-orange-400"
          animate={{ width: `${(timeLeftMs / ROUND_TIME_LIMIT_MS) * 100}%` }}
          transition={{ duration: 0.2 }}
        />
      </div>

      <motion.div
        animate={treeShake ? { rotate: [0, -8, 8, -8, 8, 0] } : { rotate: 0 }}
        transition={{ duration: 0.5 }}
        className="absolute top-24 left-1/2 -translate-x-1/2 text-9xl select-none"
      >
        🌳
      </motion.div>

      <div className="absolute top-40 left-1/2 -translate-x-1/2 w-72 h-56">
        {MANGO_POSITIONS.slice(0, mangoCount).map((pos, i) => (
          <AnimatePresence key={i}>
            {i < visibleMangoes && (
              <motion.div
                initial={{ scale: 0, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ type: 'spring', duration: 0.4 }}
                className="absolute text-4xl"
                style={{ top: `${pos.top}%`, left: `${pos.left}%` }}
              >
                🥭
              </motion.div>
            )}
          </AnimatePresence>
        ))}
      </div>

      <AnimatePresence>
        {feedback === 'correct' && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 z-30 flex items-center justify-center pointer-events-none"
          >
            <div className="text-8xl">⭐⭐⭐</div>
          </motion.div>
        )}
        {feedback === 'wrong' && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 z-30 flex items-center justify-center bg-red-200/40 pointer-events-none"
          >
            <div className="bg-white rounded-3xl px-8 py-4 shadow-2xl text-center">
              <div className="text-2xl font-bold text-red-600 mb-2">The answer was</div>
              <div className="text-6xl font-extrabold text-green-700">{mangoCount}</div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="absolute bottom-6 left-0 right-0 z-20 flex flex-wrap justify-center gap-3 px-4">
        {Array.from({ length: 10 }, (_, i) => i + 1).map((num) => (
          <motion.button
            key={num}
            whileTap={{ scale: 0.9 }}
            disabled={feedback !== null}
            onClick={() => handleAnswer(num, round, mangoCount)}
            className={`min-w-[64px] min-h-[64px] rounded-2xl text-2xl font-extrabold shadow-lg border-4 border-white text-white transition-colors ${
              selected === num
                ? feedback === 'correct'
                  ? 'bg-green-500'
                  : 'bg-red-500'
                : ['bg-purple-400', 'bg-pink-400', 'bg-blue-400', 'bg-orange-400', 'bg-teal-400'][
                    num % 5
                  ]
            }`}
          >
            {num}
          </motion.button>
        ))}
      </div>
    </div>
  );
}
