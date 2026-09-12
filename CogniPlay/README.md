# CogniPlay

**Detect Early. Intervene Early. Change Lives.**

A game-based screening aid that looks for early signals of **dyslexia**,
**dyscalculia** and **attention difficulties** in children aged 4–5, from about
ten minutes of ordinary play.

---

## ⚠️ Read this before you show it to anyone

CogniPlay is a **screening prototype, not a diagnostic tool**.

- It **cannot diagnose** dyslexia, dyscalculia or ADHD. Nobody can, from a game.
- **No trained model ships with this project.** The AI service uses a transparent
  clinical-heuristic scorer. The scores are plausible and internally consistent,
  but they are **not clinically validated** against any real cohort.
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
| `backend-python/` | FastAPI, NumPy (PyTorch/SHAP optional) | 8000 |
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
| **Python** | 3.9 or newer | `python3 --version` |
| **MongoDB** | optional — see below | `mongod --version` |
| **Docker** | optional, only for Option A | `docker --version` |

The code is deliberately written to run on **Python 3.9**, so you do not need 3.10+.

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

**1. Python AI service**
```bash
cd backend-python
python3 -m venv venv && source venv/bin/activate
pip install fastapi "uvicorn[standard]" numpy pydantic python-multipart
python main.py                      # http://localhost:8000
```

> The heavy libraries (torch, shap, opencv, reportlab) are **optional**. The service
> starts and returns correctly-shaped predictions without them, using the heuristic
> model. Install them with `pip install -r requirements.txt` to enable the full path.
> Check which mode you're in at <http://localhost:8000/health>.

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

**Scores look plausible but suspiciously round**
Expected. No trained weights ship with this project — scoring uses the documented
heuristic path. See the notice at the top of this file.

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

- The fusion model is **untrained**; heuristic weights were chosen from the
  literature's qualitative findings, not fitted to data.
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
└── docker-compose.yml
```
