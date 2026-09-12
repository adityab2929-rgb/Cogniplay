# CogniPlay

**Detect Early. Intervene Early. Change Lives.**

A game-based screening aid that looks for early signals of **dyslexia**,
**dyscalculia** and **attention difficulties** in children aged 4–5, from about
ten minutes of ordinary play.

---

## ⚠️ Read this before you show it to anyone

CogniPlay is a **screening prototype, not a diagnostic tool**.

- It **cannot diagnose** dyslexia, dyscalculia or ADHD. Nobody can, from a game.
- The repository includes **synthetic-development fixtures and demo checkpoints**
  for testing the data and scoring pipeline. They are not trained on children,
  are not clinically validated, and must not be used for real screening.
- The default scoring mode remains the transparent clinical heuristic. Synthetic
  checkpoints are loaded only when the explicit `demo` mode is selected.
- A "High" score means *"this pattern is worth showing to a professional"* — nothing more.
- Never use these outputs to group, label or stream children.

If you present this academically, say this out loud. The honesty is a strength of
the project, not a weakness — the architecture is real even though the weights are not.

---

## What's inside

| Part | Stack | Port |
|---|---|---|
| `frontend/` | React 18, TailwindCSS, Framer Motion, Chart.js, WebGazer | 3000 |
| `backend-node/` | Express, Mongoose, JWT, bcrypt | 3001 |
| `backend-python/` | FastAPI, NumPy, optional PyTorch/SHAP | 8000 |
| MongoDB | via Docker or Atlas | 27017 |

### The four games

| Game | Signal it captures | Targets |
|---|---|---|
| 🫧 **Letter Land** | b/d and p/q reversals, hesitation before choosing | Dyslexia |
| 🥭 **Number Ninja** | counting accuracy, subitizing gap between small and large sets | Dyscalculia |
| 🦋 **Butterfly Catcher** | impulsive wrong catches, focus decay over 3 minutes | ADHD |
| ✏️ **Shape Tracer** | tracing accuracy, tremor, drawing speed | Fine motor |

Eye tracking runs through the webcam **if permission is granted**. It is entirely
optional — every game works without it, and **no video is recorded or uploaded**.
Only gaze coordinates are used, and only in the browser.

---

## Before you start — prerequisites

| Need | Version | Check with |
|---|---|---|
| **Node.js** | 18 or newer | `node --version` |
| **npm** | ships with Node | `npm --version` |
| **Python** | 3.10–3.14 for PyTorch demo mode | `py --version` / `python3 --version` |
| **MongoDB** | optional — see below | `mongod --version` |
| **Docker** | optional, only for Option A | `docker --version` |

The heuristic-only service can run without PyTorch. For the included Windows
demo checkpoints, use Python 3.14 and the CPU build of PyTorch 2.14.0. Docker
uses Python 3.11 but does not install PyTorch by default.

**MongoDB is optional for a first run.** The API server starts and logs a warning
if it cannot connect. Games, scoring and the results page all work without it —
you only lose saved history and the dashboards.

Internet is needed once, for `npm install` and `pip install`.

---

## Running it

### Option A — Docker (everything at once)

```bash
cd CogniPlay
docker compose up --build
```

Then open <http://localhost:3000>.

### Option B — Locally, three terminals

**1. Python AI service — Windows with synthetic demo mode**

```powershell
cd backend-python
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu

$env:COGNIPLAY_SCORING_MODE = "demo"
.\.venv\Scripts\python.exe main.py    # http://localhost:8000
```

PowerShell execution policies do not need to be changed because the commands
invoke the virtual-environment interpreter directly rather than activating it.

**Heuristic-only mode**

```powershell
$env:COGNIPLAY_SCORING_MODE = "heuristic"
.\.venv\Scripts\python.exe main.py
```

**Linux/macOS heuristic-only service**

```bash
cd backend-python
python3 -m venv venv && source venv/bin/activate
pip install fastapi "uvicorn[standard]" numpy pydantic python-multipart
python main.py                      # http://localhost:8000
```

> PyTorch is needed only when a checkpoint-based mode is selected. Check the
> active scoring mode and whether weights loaded at <http://localhost:8000/health>.

**2. Node API**
```bash
cd backend-node
npm install
cp .env.example .env                # then edit if you use Atlas
npm run dev                         # http://localhost:3001
```

> If MongoDB isn't running the server still starts — it logs a warning and serves
> everything that doesn't need the database. That's deliberate, so a demo never
> dies on a missing Mongo.

**3. React app**
```bash
cd frontend
npm install
cp .env.example .env
npm start                           # http://localhost:3000
```

---

### Checking it actually works

Once all three are running:

1. Open <http://localhost:3000> — you should see the CogniPlay home page.
2. Open <http://localhost:8000/health> — should return JSON with `"status": "healthy"`.
3. Open <http://localhost:3001/health> — should return `{"status":"ok"}`.
4. Click **Let's Play**, enter any name, and play through. Decline the camera
   prompt if you like — the games do not need it.
5. You should land on a results page with three risk scores and explanations.

If step 5 works, the whole pipeline is working end to end.

---

## Troubleshooting

**`npm start` fails with a module or syntax error**
The React app ships without a lockfile, so a fresh install pulls the latest
compatible minor versions. Delete `node_modules` and `package-lock.json`, then
`npm install` again. If one component errors, the message names the file.

**Port already in use**
Something else is on 3000/3001/8000. Stop it, or change the port
(`PORT=` in `backend-node/.env`, `--port` on the uvicorn command).

**`ModuleNotFoundError: No module named 'fastapi'`**
The virtualenv isn't active. `source venv/bin/activate` inside `backend-python`.

**Results page says "analysis service could not be reached"**
The Python service on :8000 isn't running. That's by design — the session is still
saved and no gameplay data is lost. Start it and try again.

**`torch` cannot be imported or demo models do not load**
Use the same virtual-environment interpreter for installation and startup:
`\.venv\Scripts\python.exe -m pip install torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu`.
Then set `COGNIPLAY_SCORING_MODE` before restarting the Python service.

**Scores look plausible but suspiciously round**
In `heuristic` mode this is expected: the service uses its documented weighted
rule. In `demo` mode the CNN and LSTM are trained solely on generated data, so
their output is useful only for demonstrating the pipeline.

**Camera / eye tracking does nothing**
Also expected on many machines. It needs webcam permission on a secure origin.
Every game works without it; gaze values just become null.

---

## Configuration

Both `.env.example` files contain **placeholders only — no real credentials**.

`backend-node/.env`
```
PORT=3001
MONGODB_URI=mongodb://localhost:27017/cogniplay
JWT_SECRET=change_me_before_you_deploy_anywhere
PYTHON_AI_URL=http://localhost:8000
CORS_ORIGIN=http://localhost:3000
```

`frontend/.env`
```
REACT_APP_API_URL=http://localhost:3001
REACT_APP_FIREBASE_API_KEY=your_firebase_api_key
...
```

**Firebase is optional.** Leave the placeholders in and the app buffers gameplay
events in memory instead — everything works, including the final analysis.

> 🔐 Change `JWT_SECRET` before this is reachable by anyone but you.

---

## How a session flows

```
Child plays 4 games (~10 min)
        │  every click, answer, catch and stroke is logged
        ▼
GameFlow.jsx assembles one session JSON
        ▼
POST /api/submit-game        (Express, saves raw session, status=processing)
        ▼
POST /predict-learning-pattern   (FastAPI)
        │  extract_features → fusion model → SHAP explanation → gaze heatmap
        ▼
Scores + explanations saved, child's latest risk scores updated
        ▼
Results page: three risk cards, contributing factors, heatmap, next steps
```

If the Python service is unreachable, Express still returns **200** with
`status: "pending"` and the child sees a friendly ending rather than an error.
No gameplay data is lost.

---

## Scoring modes and demo checkpoints

The Python service reads `COGNIPLAY_SCORING_MODE` at startup.

| Mode | Checkpoints loaded | Final score behaviour |
|---|---|---|
| `heuristic` (default) | None | All three indicators use the transparent heuristic. |
| `demo` | `training/demo_models/dyslexia_cnn.pt` and `adhd_lstm.pt` | Dyslexia = 60% CNN + 40% heuristic; ADHD = 50% LSTM + 50% heuristic; dyscalculia remains heuristic-only. |
| `validated` | `saved_models/dyslexia_cnn.pt` and `adhd_lstm.pt` | Uses the same blends, but this mode is reserved for independently validated checkpoints. |

The Results page displays an explicit warning whenever `demo` mode is active.
The percentage is a 0–1 score converted to a percentage; it is not a
probability of diagnosis.

### Synthetic dataset and demo training

`backend-python/training/synthetic_data/` contains deterministic development
fixtures generated from game-behaviour assumptions:

| Artifact | Size | Purpose |
|---|---:|---|
| `raw_sessions.jsonl` | 10,000 sessions | Complete frontend-compatible mock sessions across eight profiles, including typical/no-flag cases. |
| `labels.csv` | 10,000 rows | Synthetic dyslexia, dyscalculia, and ADHD labels. |
| `cnn_training.csv` | 10,000 rows | One 20-feature input vector per session and its synthetic dyslexia label. |
| `lstm_training.csv` | 60,000 rows | Six timesteps per session, producing 10,000 `(6, 4)` LSTM inputs and synthetic ADHD labels. |
| `manifest.json` | 1 file | Seed, exact feature order, shapes, and file checksums. |

Generate and validate the fixtures from `backend-python`:

```powershell
.\.venv\Scripts\python.exe training/generate_synthetic_data.py
.\.venv\Scripts\python.exe training/validate_synthetic_data.py
```

Train the demo checkpoints:

```powershell
.\.venv\Scripts\python.exe training/train_models.py --data-dir training/synthetic_data
```

The training script writes to `training/demo_models/` and refuses to install
synthetic-trained weights in `saved_models/`.

---

## Design decisions worth defending in a viva

- **Graceful degradation everywhere.** Missing camera, missing Firebase, missing
  MongoDB, missing PyTorch — each one degrades to a working fallback instead of a
  crash. A screening tool used in an Indian UKG classroom cannot assume a good webcam,
  a stable connection, or a 2.5 GB ML install.
- **Explainability is not optional.** A risk score a parent cannot interrogate is
  worse than no score. Every condition ships its top contributing factors in plain
  English.
- **Accessibility in the result UI.** Risk levels always pair colour with an icon
  and a word, and the categorical palette is validated for colour-vision deficiency —
  a parent who is colour-blind must read the same result everyone else does.
- **The disclaimer is placed above the scores**, not buried under them.

---

### Missing data is never read as impairment

If a child does not finish a game, the condition that game feeds is returned with
`insufficient_data` set rather than a score. A skipped Number Ninja round yields
*"we have nothing to judge"*, not a mid-range dyscalculia score. The results page
says so explicitly, because a "Low" that actually means "unknown" is the most
dangerous output a screening tool can produce.

## Known limitations

- The heuristic weights were chosen from qualitative findings, not fitted to
  clinical outcome data.
- Included CNN/LSTM checkpoints were trained only on synthetic fixtures. More
  synthetic rows improve a software demonstration, not real-world accuracy,
  calibration, sensitivity, or specificity.
- Norms are not age-standardised — a 4-year-old and a 5-year-old are scored identically.
- WebGazer accuracy varies widely with lighting and camera quality.
- No accessibility audit has been done on the games themselves.
- Not COPPA/GDPR compliant as-is: real deployment needs parental consent flows,
  data retention limits, and encryption at rest.

---

## Project layout

```
CogniPlay/
├── frontend/          React app — games, dashboards, results
├── backend-node/      Express API — auth, sessions, reports
├── backend-python/    FastAPI — feature extraction, scoring, explanation, PDF
│   └── training/      Synthetic fixtures, validator, demo trainer and demo models
└── docker-compose.yml
```
