import React, { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { logGameEvent } from '../utils/firebase';
import { initEyeTracking, stopEyeTracking, getGazeData } from '../utils/eyeTracking';

const GAME_KEY = 'letter_land';
const ALL_LETTERS = ['b', 'd', 'p', 'q', 'a', 'e', 'i', 'o'];
const ROUND_TARGETS = ['b', 'd', 'p', 'q'];
const ROUND_DURATION_SEC = 45;
const TOTAL_DURATION_SEC = 180;
const NUM_BUBBLES = 8;

const BUBBLE_COLORS = [
  'bg-pink-300', 'bg-yellow-300', 'bg-green-300', 'bg-purple-300',
  'bg-orange-300', 'bg-teal-300', 'bg-red-300', 'bg-indigo-300',
];

function randomPosition() {
  return {
    top: 10 + Math.random() * 65,
    left: 5 + Math.random() * 80,
  };
}

function makeBubble(id) {
  return {
    id,
    letter: ALL_LETTERS[Math.floor(Math.random() * ALL_LETTERS.length)],
    color: BUBBLE_COLORS[Math.floor(Math.random() * BUBBLE_COLORS.length)],
    pos: randomPosition(),
    spawnTime: Date.now(),
    hoverStart: null,
    flash: null, // 'correct' | 'wrong' | null
  };
}

function makeInitialBubbles() {
  const arr = [];
  for (let i = 0; i < NUM_BUBBLES; i++) {
    arr.push(makeBubble(`b-${i}-${Date.now()}-${Math.random()}`));
  }
  return arr;
}

export default function LetterLand({ childId, onComplete }) {
  const [bubbles, setBubbles] = useState(makeInitialBubbles);
  const [score, setScore] = useState(0);
  const [timeLeft, setTimeLeft] = useState(TOTAL_DURATION_SEC);
  const [roundIndex, setRoundIndex] = useState(0);
  const [finished, setFinished] = useState(false);

  const targetLetter = ROUND_TARGETS[Math.min(roundIndex, ROUND_TARGETS.length - 1)];

  const statsRef = useRef({
    total_clicks: 0,
    correct_clicks: 0,
    wrong_clicks: 0,
    response_times: [],
    letter_errors: [],
    bd_confusion_count: 0,
    pq_confusion_count: 0,
    hesitation_times: [],
  });

  const bubbleIdRef = useRef(NUM_BUBBLES);
  const finishedRef = useRef(false);
  const gameStartRef = useRef(Date.now());

  // Eye tracking lifecycle
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        await initEyeTracking(childId, GAME_KEY);
      } catch (e) {
        // swallow
      }
    })();
    return () => {
      active = false;
      try {
        stopEyeTracking();
      } catch (e) {
        // swallow
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const finishGame = useCallback(() => {
    if (finishedRef.current) return;
    finishedRef.current = true;
    setFinished(true);

    const s = statsRef.current;
    const accuracy = s.total_clicks > 0 ? s.correct_clicks / s.total_clicks : 0;
    const avg_response_time_ms =
      s.response_times.length > 0
        ? s.response_times.reduce((a, b) => a + b, 0) / s.response_times.length
        : 0;
    const hesitation_avg_ms =
      s.hesitation_times.length > 0
        ? s.hesitation_times.reduce((a, b) => a + b, 0) / s.hesitation_times.length
        : 0;

    const payload = {
      total_clicks: s.total_clicks,
      correct_clicks: s.correct_clicks,
      wrong_clicks: s.wrong_clicks,
      accuracy,
      avg_response_time_ms,
      letter_errors: s.letter_errors,
      bd_confusion_count: s.bd_confusion_count,
      pq_confusion_count: s.pq_confusion_count,
      hesitation_avg_ms,
    };

    setTimeout(() => {
      if (typeof onComplete === 'function') {
        onComplete(payload);
      }
    }, 1600);
  }, [onComplete]);

  // Main countdown timer
  useEffect(() => {
    if (finished) return undefined;
    const interval = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          finishGame();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [finished, finishGame]);

  // Round progression
  useEffect(() => {
    if (finished) return undefined;
    const elapsed = TOTAL_DURATION_SEC - timeLeft;
    const newRoundIndex = Math.min(
      Math.floor(elapsed / ROUND_DURATION_SEC),
      ROUND_TARGETS.length - 1
    );
    if (newRoundIndex !== roundIndex) {
      setRoundIndex(newRoundIndex);
    }
  }, [timeLeft, roundIndex, finished]);

  const respawnBubble = useCallback((oldId) => {
    setBubbles((prev) =>
      prev.map((b) => {
        if (b.id !== oldId) return b;
        bubbleIdRef.current += 1;
        return makeBubble(`b-${bubbleIdRef.current}-${Date.now()}-${Math.random()}`);
      })
    );
  }, []);

  const handleHoverStart = useCallback((id) => {
    setBubbles((prev) =>
      prev.map((b) => (b.id === id ? { ...b, hoverStart: b.hoverStart || Date.now() } : b))
    );
  }, []);

  const handleClick = useCallback(
    (bubble) => {
      if (finished) return;
      const now = Date.now();
      const responseTimeMs = now - bubble.spawnTime;
      const hesitationMs = bubble.hoverStart ? now - bubble.hoverStart : 0;
      const isCorrect = bubble.letter === targetLetter;

      const s = statsRef.current;
      s.total_clicks += 1;
      s.response_times.push(responseTimeMs);
      s.hesitation_times.push(hesitationMs);

      if (isCorrect) {
        s.correct_clicks += 1;
      } else {
        s.wrong_clicks += 1;
        s.letter_errors.push({
          shown: targetLetter,
          clicked: bubble.letter,
          time_ms: responseTimeMs,
        });
        if (
          (targetLetter === 'b' && bubble.letter === 'd') ||
          (targetLetter === 'd' && bubble.letter === 'b')
        ) {
          s.bd_confusion_count += 1;
        }
        if (
          (targetLetter === 'p' && bubble.letter === 'q') ||
          (targetLetter === 'q' && bubble.letter === 'p')
        ) {
          s.pq_confusion_count += 1;
        }
      }

      let gaze = { x: null, y: null };
      try {
        gaze = getGazeData() || { x: null, y: null };
      } catch (e) {
        gaze = { x: null, y: null };
      }

      logGameEvent(childId, GAME_KEY, {
        type: 'letter_click',
        letter_shown: targetLetter,
        letter_clicked: bubble.letter,
        is_correct: isCorrect,
        response_time_ms: responseTimeMs,
        hesitation_ms: hesitationMs,
        gaze_x: gaze.x,
        gaze_y: gaze.y,
      });

      if (isCorrect) {
        setScore((prevScore) => prevScore + 1);
      }

      setBubbles((prev) =>
        prev.map((b) => (b.id === bubble.id ? { ...b, flash: isCorrect ? 'correct' : 'wrong' } : b))
      );

      setTimeout(() => {
        respawnBubble(bubble.id);
      }, 350);
    },
    [childId, finished, targetLetter, respawnBubble]
  );

  if (finished) {
    return (
      <div className="w-full h-full min-h-[600px] flex flex-col items-center justify-center bg-sky-100 rounded-3xl">
        <motion.div
          initial={{ scale: 0.5, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: 'spring', duration: 0.6 }}
          className="text-center"
        >
          <div className="text-7xl mb-4">Amazing! ⭐</div>
          <div className="text-3xl font-bold text-sky-700">Score: {score}</div>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="relative w-full h-full min-h-[600px] overflow-hidden rounded-3xl bg-gradient-to-b from-sky-200 to-sky-100">
      <div className="absolute top-4 left-4 z-20 bg-white/80 rounded-2xl px-5 py-2 shadow-lg">
        <span className="text-2xl font-extrabold text-sky-700">Score: {score}</span>
      </div>
      <div className="absolute top-4 right-4 z-20 bg-white/80 rounded-2xl px-5 py-2 shadow-lg">
        <span className="text-2xl font-extrabold text-sky-700">{timeLeft}s</span>
      </div>

      <div className="absolute top-20 left-0 right-0 z-20 flex justify-center">
        <div className="bg-yellow-200 rounded-3xl px-8 py-4 shadow-xl">
          <h1 className="text-2xl md:text-3xl font-extrabold text-center text-sky-800">
            POP ALL THE '{targetLetter.toUpperCase()}' BUBBLES! 🎯
          </h1>
        </div>
      </div>

      <AnimatePresence>
        {bubbles.map((bubble) => (
          <motion.button
            key={bubble.id}
            initial={{ scale: 0, opacity: 0 }}
            animate={{
              scale: bubble.flash ? [1, 1.3, 0] : 1,
              opacity: bubble.flash ? [1, 1, 0] : 1,
              y: bubble.flash ? 0 : [0, -30, 0],
              x: bubble.flash === 'wrong' ? [0, -10, 10, -10, 10, 0] : 0,
            }}
            exit={{ scale: 0, opacity: 0 }}
            transition={
              bubble.flash
                ? { duration: 0.35 }
                : { y: { duration: 2, repeat: Infinity }, default: { duration: 0.3 } }
            }
            style={{ top: `${bubble.pos.top}%`, left: `${bubble.pos.left}%`, minWidth: 72, minHeight: 72 }}
            className={`absolute z-10 w-20 h-20 md:w-24 md:h-24 rounded-full shadow-2xl flex items-center justify-center text-3xl md:text-4xl font-extrabold text-white border-4 border-white ${
              bubble.color
            } ${bubble.flash === 'correct' ? 'ring-4 ring-green-400' : ''} ${
              bubble.flash === 'wrong' ? 'ring-4 ring-red-400' : ''
            }`}
            onMouseEnter={() => handleHoverStart(bubble.id)}
            onClick={() => handleClick(bubble)}
          >
            {bubble.letter}
          </motion.button>
        ))}
      </AnimatePresence>
    </div>
  );
}
