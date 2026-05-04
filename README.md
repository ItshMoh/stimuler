# Stimuler Speech Assessment

Stimuler is a speech assessment web app that checks whether a learner spoke the selected target sentence correctly. It combines live transcription, strict word-level matching, pronunciation approximation, fluency analysis, pause detection, filler detection, and ambient noise monitoring.

The main goal is to avoid inflated scores when a user speaks confidently but says the wrong sentence. Accuracy is treated as a strict lexical comparison against the selected prompt, while delivery and pronunciation are scored separately.

## Problem Being Solved

Generic speech scoring can give a reasonable score even when the spoken sentence does not match the assigned target. This project is built around a stricter assessment model:

- The user must choose a predefined prompt.
- The system listens to the user's speech through the browser microphone.
- Deepgram provides live transcription, word timings, confidence, and filler information.
- The backend compares the transcript against the target sentence.
- The frontend shows score cards, transcript feedback, word-level mismatch feedback, pauses, fillers, and reliability warnings.

The scoring is intentionally split so the app can explain whether the user failed because of wrong words, weak pronunciation approximation, poor fluency, long pauses, fillers, or noisy recording conditions.

## Scoring Approach

### Accuracy Score

Accuracy answers the question: did the user say the correct words?

The backend normalizes the target sentence and transcript, tokenizes both, and aligns the words. Each aligned word is classified as one of:

- Match: the spoken word matches the target word.
- Substitution: the user said a different word.
- Omission: the user skipped a target word.
- Insertion: the user added extra words.

The strict accuracy score is based on these alignment results. Speaking fluently does not increase this score if the words are wrong. This is the core safeguard against giving a high score for an unrelated sentence.

### Pronunciation Score

Pronunciation is an approximation, not a true phoneme-level clinical assessment.

The backend converts the target sentence and transcript into simplified phonetic representations, then compares them with phonetic Levenshtein distance. It also uses Deepgram word confidence when available. The final pronunciation score combines:

- Phonetic similarity between the target and transcript.
- Average Deepgram confidence across recognized words.
- Transcript reliability based on whether enough speech was recognized.

This means pronunciation scoring is most useful when the transcript is close to the target. If the user says the wrong words, the pronunciation score should be interpreted together with the strict accuracy score.

### Fluency Score

Fluency answers the question: how smoothly did the user speak?

The backend uses Deepgram word timestamps to calculate:

- Speaking duration.
- Words per minute.
- Rhythm quality.
- Pause patterns.

The fluency score is separate from accuracy. A user can be fluent while saying the wrong sentence, so fluency does not override lexical mismatch.

### Pause Score

Pause scoring uses gaps between word timestamps.

The backend separates pauses into:

- Mild hesitations.
- Awkward pauses.

Long or frequent awkward pauses reduce the pause score. Natural short pauses do not carry the same penalty.

### Filler Score

The app detects common filler words such as "um", "uh", "like", and similar hesitation markers. More fillers reduce the filler score and are shown in the feedback UI.

### Noise And Reliability

The frontend monitors ambient microphone input before and during recording. If the background noise is too high, the user sees a warning before the score is finalized.

Noise monitoring is used as a reliability signal, not as a direct score penalty. The goal is to warn the user that the recording environment may make transcription and scoring less reliable.

The backend also returns reliability warnings when transcript confidence is low or when too few words are detected.

## Live Transcription Flow

The app uses WebSockets for live transcription:

1. The browser captures microphone chunks with `MediaRecorder`.
2. Audio chunks stream to the FastAPI backend over WebSocket.
3. The backend relays audio to Deepgram's live transcription WebSocket.
4. Interim and final transcript updates are sent back to the frontend.
5. When the user stops recording, the backend sends a finalize message to Deepgram.
6. The backend waits briefly using `STREAM_FINALIZE_WAIT_SECONDS`.
7. The final transcript is scored and returned to the frontend.

`STREAM_FINALIZE_WAIT_SECONDS` gives Deepgram a short window to flush the final transcript segment. A higher value can make final transcripts more complete but slower. A lower value can make feedback faster but may miss the last words.

## Architecture

```text
frontend/
  React + TypeScript + Vite
  Microphone capture
  Live transcript UI
  Noise monitoring
  Assessment feedback UI

backend/
  FastAPI
  Deepgram integration
  WebSocket streaming
  Strict accuracy scoring
  Pronunciation approximation
  Fluency, pause, and filler scoring
```

## Tech Stack

- Frontend: React, TypeScript, Vite
- Backend: FastAPI, Uvicorn, Python
- Speech-to-text: Deepgram
- Streaming: Browser WebSocket, backend WebSocket, Deepgram live transcription
- Deployment target: Vercel for frontend, DigitalOcean App Platform for backend

## Important Environment Variables

Backend:

```env
FRONTEND_ORIGINS=http://localhost:5173
DEEPGRAM_API_KEY=
DEEPGRAM_MODEL=nova-3
STREAM_FINALIZE_WAIT_SECONDS=1.2
```

Frontend:

```env
VITE_API_BASE_URL=http://localhost:8000
```

For production, `FRONTEND_ORIGINS` must be the deployed Vercel frontend URL, and `VITE_API_BASE_URL` must be the deployed backend URL.

## Deployment

The intended deployment setup is:

- Backend: DigitalOcean App Platform
- Frontend: Vercel

Detailed deployment steps are in [DEPLOYMENT.md](./DEPLOYMENT.md).

## Installation And Local Run

### Backend

From the project root:

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set `DEEPGRAM_API_KEY` in `backend/.env`, then run:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```text
http://localhost:8000/api/health
```

### Frontend

In a second terminal:

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open:

```text
http://localhost:5173
```

## Verification

Run backend tests:

```bash
python3 -m pytest backend
```

Build the frontend:

```bash
cd frontend
npm run build
```

## Repository Notes

- `backend/test_scoring.py` covers the scoring logic.
- `backend/scoring.py` contains strict accuracy, pronunciation approximation, fluency, pause, and filler scoring.
- `backend/streaming.py` contains the live transcription and final assessment flow.
- `frontend/src/App.tsx` contains the main recording and feedback UI.
