import React, { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { logGameEvent } from '../utils/firebase';
import { initEyeTracking, stopEyeTracking, getGazeData } from '../utils/eyeTracking';

const GAME_KEY = 'butterfly_game';
const TOTAL_DURATION_SEC = 180;
const INTERVAL_SEC = 30;
const NUM_INTERVALS = TOTAL_DURATION_SEC / INTERVAL_SEC;
const MIN_BUTTERFLIES = 5;
const MAX_BUTTERFLIES = 8;

function speedForMinute(minute) {
  if (minute <= 1) return 1.0;
  if (minute === 2) return 1.3;
  return 1.6;
}

function randomEdgeStart() {
  const edge = Math.floor(Math.random() * 4);
  switch (edge) {
    case 0:
      return { x: Math.random() * 100, y: -10 };
    case 1:
      return { x: 110, y: Math.random() * 100 };
    case 2:
      return { x: Math.random() * 100, y: 110 };
    default:
      return { x: -10, y: Math.random() * 100 };
  }
}

function randomPathPoints() {
  const points = [];
  const numPoints = 4 + Math.floor(Math.random() * 3);
  for (let i = 0; i < numPoints; i++) {
    points.push({
      x: 10 + Math.random() * 80,
      y: 10 + Math.random() * 80,
    });
  }
  return points;
}

function makeButterfly(id) {
  const isBlue = Math.random() < 0.6;
  const start = randomEdgeStart();
  return {
    id,
    color: isBlue ? 'blue' : 'red',
    start,
    path: randomPathPoints(),
    duration: 6 + Math.random() * 4,
    spawnTime: Date.now(),
    caught: false,
  };
}

export default function ButterflyGame({ childId, onComplete }) {
  const [butterflies, setButterflies] = useState([]);
  const [score, setScore] = useState(0);
  const [timeLeft, setTimeLeft] = useState(TOTAL_DURATION_SEC);
  const [attentionMeter, setAttentionMeter] = useState(100);
  const [redFlash, setRedFlash] = useState(false);
  const [finished, setFinished] = useState(false);

  const finishedRef = useRef(false);
  const butterflyIdRef = useRef(0);
  const spawnIntervalRef = useRef(null);
  const countdownIntervalRef = useRef(null);
  const intervalSummaryTimeoutRef = useRef(null);

  const statsRef = useRef({
    total_catches: 0,
    correct_catches: 0,
    wrong_catches: 0,
    response_times: [],
    interval_stats: [], // {interval, correct, wrong, responseTimes:[]}
  });
  const currentIntervalRef = useRef({ interval: 1, correct: 0, wrong: 0, responseTimes: [] });

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
    if (spawnIntervalRef.current) clearInterval(spawnIntervalRef.current);
    if (countdownIntervalRef.current) clearInterval(countdownIntervalRef.current);
    if (intervalSummaryTimeoutRef.current) clearInterval(intervalSummaryTimeoutRef.current);
  }, []);

  useEffect(() => {
    return () => clearAllTimers();
  }, [clearAllTimers]);

  const finishGame = useCallback(() => {
    if (finishedRef.current) return;
    finishedRef.current = true;
    clearAllTimers();
    setFinished(true);

    // flush last interval
    const s = statsRef.current;
    const ci = currentIntervalRef.current;
    const avgRt =
      ci.responseTimes.length > 0
        ? ci.responseTimes.reduce((a, b) => a + b, 0) / ci.responseTimes.length
        : 0;
    const total = ci.correct + ci.wrong;
    const attention_score = total > 0 ? ci.correct / total : 0;
    s.interval_stats.push({
      interval: ci.interval,
      correct: ci.correct,
      wrong: ci.wrong,
      score: attention_score,
    });

    const total_catches = s.total_catches;
    const accuracy = total_catches > 0 ? s.correct_catches / total_catches : 0;
    const impulsivity_score = total_catches > 0 ? s.wrong_catches / total_catches : 0;
    const avg_response_time_ms =
      s.response_times.length > 0
        ? s.response_times.reduce((a, b) => a + b, 0) / s.response_times.length
        : 0;

    const scores = s.interval_stats.map((it) => it.score);
    const half = Math.floor(scores.length / 2);
    const firstHalf = scores.slice(0, half);
    const secondHalf = scores.slice(half);
    const avg = (arr) => (arr.length > 0 ? arr.reduce((a, b) => a + b, 0) / arr.length : 0);
    const performance_drop = avg(firstHalf) - avg(secondHalf);

    const payload = {
      total_catches,
      correct_catches: s.correct_catches,
      wrong_catches: s.wrong_catches,
      accuracy,
      impulsivity_score,
      attention_by_interval: s.interval_stats,
      performance_drop,
      avg_response_time_ms,
    };

    setTimeout(() => {
      if (typeof onComplete === 'function') {
        onComplete(payload);
      }
    }, 1500);
  }, [clearAllTimers, onComplete]);

  // Countdown + interval summary
  useEffect(() => {
    countdownIntervalRef.current = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          finishGame();
          return 0;
        }
        const elapsed = TOTAL_DURATION_SEC - prev + 1;
        if (elapsed % INTERVAL_SEC === 0 && elapsed < TOTAL_DURATION_SEC) {
          const ci = currentIntervalRef.current;
          const avgRt =
            ci.responseTimes.length > 0
              ? ci.responseTimes.reduce((a, b) => a + b, 0) / ci.responseTimes.length
              : 0;
          const total = ci.correct + ci.wrong;
          const attention_score = total > 0 ? ci.correct / total : 0;
          statsRef.current.interval_stats.push({
            interval: ci.interval,
            correct: ci.correct,
            wrong: ci.wrong,
            score: attention_score,
          });
          logGameEvent(childId, GAME_KEY, {
            type: 'interval_summary',
            interval_number: ci.interval,
            correct_catches: ci.correct,
            wrong_catches: ci.wrong,
            average_response_time_ms: avgRt,
            attention_score,
          });
          setAttentionMeter(Math.round(attention_score * 100));
          currentIntervalRef.current = {
            interval: ci.interval + 1,
            correct: 0,
            wrong: 0,
            responseTimes: [],
          };
        }
        return prev - 1;
      });
    }, 1000);
    return () => {
      if (countdownIntervalRef.current) clearInterval(countdownIntervalRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [childId, finishGame]);

  // Spawn butterflies to maintain count between MIN and MAX
  useEffect(() => {
    const spawnOne = () => {
      butterflyIdRef.current += 1;
      const nb = makeButterfly(`bf-${butterflyIdRef.current}`);
      setButterflies((prev) => {
        if (prev.length >= MAX_BUTTERFLIES) return prev;
        return [...prev, nb];
      });
    };

    for (let i = 0; i < MIN_BUTTERFLIES; i++) {
      spawnOne();
    }

    spawnIntervalRef.current = setInterval(() => {
      setButterflies((prev) => {
        if (prev.length < MAX_BUTTERFLIES && Math.random() < 0.5) {
          butterflyIdRef.current += 1;
          return [...prev, makeButterfly(`bf-${butterflyIdRef.current}`)];
        }
        return prev;
      });
    }, 1800);

    return () => {
      if (spawnIntervalRef.current) clearInterval(spawnIntervalRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const removeButterfly = useCallback((id) => {
    setButterflies((prev) => prev.filter((b) => b.id !== id));
  }, []);

  const handleCatch = useCallback(
    (butterfly) => {
      if (finishedRef.current || butterfly.caught) return;

      const minuteInGame = Math.floor((TOTAL_DURATION_SEC - timeLeft) / 60) + 1;
      const gameSpeed = speedForMinute(minuteInGame);
      const responseTimeMs = Date.now() - butterfly.spawnTime;
      const isCorrect = butterfly.color === 'blue';

      const s = statsRef.current;
      s.total_catches += 1;
      s.response_times.push(responseTimeMs);
      const ci = currentIntervalRef.current;
      ci.responseTimes.push(responseTimeMs);
      if (isCorrect) {
        s.correct_catches += 1;
        ci.correct += 1;
      } else {
        s.wrong_catches += 1;
        ci.wrong += 1;
        setRedFlash(true);
        setTimeout(() => setRedFlash(false), 300);
      }

      let gaze = { x: null, y: null };
      try {
        gaze = getGazeData() || { x: null, y: null };
      } catch (e) {
        gaze = { x: null, y: null };
      }

      logGameEvent(childId, GAME_KEY, {
        type: 'butterfly_catch',
        butterfly_color: butterfly.color,
        should_catch: 'blue',
        is_correct: isCorrect,
        response_time_ms: responseTimeMs,
        minute_in_game: minuteInGame,
        game_speed: gameSpeed,
        gaze_x: gaze.x,
        gaze_y: gaze.y,
      });

      if (isCorrect) {
        setScore((prev) => prev + 1);
      }

      setButterflies((prev) =>
        prev.map((b) => (b.id === butterfly.id ? { ...b, caught: true } : b))
      );
      setTimeout(() => removeButterfly(butterfly.id), 300);
    },
    [childId, timeLeft, removeButterfly]
  );

  if (finished) {
    return (
      <div className="w-full h-full min-h-[600px] flex flex-col items-center justify-center bg-purple-100 rounded-3xl">
        <motion.div
          initial={{ scale: 0.5, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: 'spring', duration: 0.6 }}
          className="text-center"
        >
          <div className="text-7xl mb-4">Well Done! 🦋</div>
          <div className="text-3xl font-bold text-purple-800">Score: {score}</div>
        </motion.div>
      </div>
    );
  }

  const minuteInGame = Math.floor((TOTAL_DURATION_SEC - timeLeft) / 60) + 1;
  const gameSpeed = speedForMinute(minuteInGame);

  return (
    <div
      className={`relative w-full h-full min-h-[600px] overflow-hidden rounded-3xl transition-colors duration-300 ${
        redFlash ? 'bg-red-300' : 'bg-gradient-to-b from-purple-200 to-purple-100'
      }`}
      style={{ backgroundColor: redFlash ? undefined : undefined }}
    >
      <div className="absolute top-4 left-4 z-20 bg-white/80 rounded-2xl px-5 py-2 shadow-lg">
        <span className="text-xl font-extrabold text-purple-800">Score: {score}</span>
      </div>
      <div className="absolute top-4 right-4 z-20 bg-white/80 rounded-2xl px-5 py-2 shadow-lg">
        <span className="text-xl font-extrabold text-purple-800">{timeLeft}s</span>
      </div>

      <div className="absolute top-20 left-0 right-0 z-20 flex justify-center">
        <div className="bg-blue-200 rounded-3xl px-8 py-3 shadow-xl">
          <h1 className="text-xl md:text-2xl font-extrabold text-center text-purple-900">
            Catch the BLUE butterflies only! 🦋
          </h1>
        </div>
      </div>

      <div className="absolute top-32 left-1/2 -translate-x-1/2 w-64 z-20">
        <div className="text-center text-sm font-bold text-purple-700 mb-1">Attention</div>
        <div className="w-full h-4 bg-white/60 rounded-full overflow-hidden">
          <motion.div
            className="h-full bg-gradient-to-r from-green-400 to-emerald-500"
            animate={{ width: `${attentionMeter}%` }}
            transition={{ duration: 0.4 }}
          />
        </div>
      </div>

      <AnimatePresence>
        {butterflies.map((b) => (
          <motion.button
            key={b.id}
            initial={{ left: `${b.start.x}%`, top: `${b.start.y}%`, opacity: 0, scale: 1 }}
            animate={{
              left: b.caught ? undefined : b.path.map((p) => `${p.x}%`),
              top: b.caught ? undefined : b.path.map((p) => `${p.y}%`),
              opacity: b.caught ? 0 : 1,
              scale: b.caught ? [1, 1.6, 0] : 1,
            }}
            exit={{ opacity: 0, scale: 0 }}
            transition={{
              left: { duration: b.duration / gameSpeed, repeat: Infinity, repeatType: 'reverse' },
              top: { duration: b.duration / gameSpeed, repeat: Infinity, repeatType: 'reverse' },
              opacity: { duration: 0.3 },
              scale: { duration: 0.3 },
            }}
            onClick={() => handleCatch(b)}
            className="absolute z-10 text-5xl min-w-[64px] min-h-[64px] flex items-center justify-center select-none"
            style={{
              filter:
                b.color === 'blue'
                  ? 'hue-rotate(200deg) saturate(3)'
                  : 'hue-rotate(-20deg) saturate(3)',
            }}
          >
            🦋
          </motion.button>
        ))}
      </AnimatePresence>
    </div>
  );
}
