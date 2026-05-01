import { useEffect, useMemo, useRef, useState } from 'react'
import './App.css'

type ApiStatus = 'checking' | 'online' | 'offline'
type PromptCategory = 'All' | 'IELTS' | 'Professional'
type RecordingStatus =
  | 'idle'
  | 'requesting'
  | 'recording'
  | 'uploading'
  | 'uploaded'
  | 'error'

type Prompt = {
  id: string
  text: string
  category: Exclude<PromptCategory, 'All'>
  difficulty: string
}

type UploadResult = {
  prompt_id: string
  target_text: string
  filename: string
  content_type: string
  size_bytes: number
  transcript: string
  confidence: number | null
  deepgram_model: string
  words: TranscribedWord[]
  scores: {
    accuracy: number
    pronunciation: number
    fluency: number
    pause: number
    filler: number
  }
  metrics: AssessmentMetrics
  fillers: FillerEvent[]
  pauses: PauseEvent[]
  word_feedback: WordFeedback[]
  explanation: string
  fluency_explanation: string
  pronunciation_explanation: string
  message: string
}

type TranscribedWord = {
  word: string
  punctuated_word: string | null
  start: number | null
  end: number | null
  confidence: number | null
}

type AssessmentMetrics = {
  target_word_count: number
  spoken_word_count: number
  match_count: number
  substitution_count: number
  omission_count: number
  insertion_count: number
  words_per_minute: number | null
  speaking_duration_seconds: number | null
  filler_count: number
  pause_count: number
  awkward_pause_count: number
  mild_hesitation_count: number
  rhythm_score: number
  phonetic_similarity: number
  average_word_confidence: number | null
  target_phonetic: string
  transcript_phonetic: string
}

type WordFeedback = {
  target_word: string | null
  spoken_word: string | null
  status: 'match' | 'substitution' | 'omission' | 'insertion'
}

type FillerEvent = {
  word: string
  start: number | null
  end: number | null
}

type PauseEvent = {
  type: 'mild_hesitation' | 'awkward_pause'
  duration_seconds: number
  after_word: string
  before_word: string
  start: number | null
  end: number | null
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
const categories: PromptCategory[] = ['All', 'IELTS', 'Professional']

function App() {
  const [apiStatus, setApiStatus] = useState<ApiStatus>('checking')
  const [prompts, setPrompts] = useState<Prompt[]>([])
  const [selectedCategory, setSelectedCategory] =
    useState<PromptCategory>('All')
  const [selectedPromptId, setSelectedPromptId] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [recordingStatus, setRecordingStatus] =
    useState<RecordingStatus>('idle')
  const [recordingError, setRecordingError] = useState('')
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null)
  const [liveTranscript, setLiveTranscript] = useState('')

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const websocketRef = useRef<WebSocket | null>(null)
  const timerRef = useRef<number | null>(null)

  useEffect(() => {
    const loadPrompts = async () => {
      try {
        const healthResponse = await fetch(`${API_BASE_URL}/api/health`)

        if (!healthResponse.ok) {
          throw new Error('Health check failed')
        }

        const promptsResponse = await fetch(`${API_BASE_URL}/api/prompts`)

        if (!promptsResponse.ok) {
          throw new Error('Prompt request failed')
        }

        const data: { prompts: Prompt[] } = await promptsResponse.json()
        setPrompts(data.prompts)
        setApiStatus('online')
      } catch (error) {
        setApiStatus('offline')
        setErrorMessage(
          error instanceof Error ? error.message : 'Unable to reach backend',
        )
      }
    }

    loadPrompts()
  }, [])

  useEffect(() => {
    return () => {
      stopTimer()
      stopStream()
      websocketRef.current?.close()
    }
  }, [])

  const filteredPrompts = useMemo(() => {
    if (selectedCategory === 'All') {
      return prompts
    }

    return prompts.filter((prompt) => prompt.category === selectedCategory)
  }, [prompts, selectedCategory])

  const selectedPrompt = prompts.find((prompt) => prompt.id === selectedPromptId)
  const isBusy =
    recordingStatus === 'requesting' ||
    recordingStatus === 'recording' ||
    recordingStatus === 'uploading'

  function startTimer() {
    stopTimer()
    setElapsedSeconds(0)
    timerRef.current = window.setInterval(() => {
      setElapsedSeconds((seconds) => seconds + 1)
    }, 1000)
  }

  function stopTimer() {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
  }

  function stopStream() {
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
  }

  function getLiveTranscriptionUrl(promptId: string) {
    const url = new URL(API_BASE_URL)
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    url.pathname = `/api/transcribe/live/${promptId}`
    return url.toString()
  }

  function getPreferredMimeType() {
    const mimeTypes = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/mp4',
      'audio/ogg;codecs=opus',
    ]

    return mimeTypes.find((mimeType) => MediaRecorder.isTypeSupported(mimeType))
  }

  async function startRecording() {
    if (!selectedPrompt || isBusy) {
      return
    }

    try {
      setRecordingStatus('requesting')
      setRecordingError('')
      setUploadResult(null)
      setLiveTranscript('')

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const websocket = new WebSocket(getLiveTranscriptionUrl(selectedPrompt.id))
      websocket.binaryType = 'arraybuffer'
      websocketRef.current = websocket

      websocket.onmessage = (event) => {
        const data = JSON.parse(event.data)

        if (data.type === 'ready') {
          return
        }

        if (data.type === 'transcript') {
          setLiveTranscript(data.transcript)
          return
        }

        if (data.type === 'assessment') {
          setUploadResult(data.result)
          setLiveTranscript(data.result.transcript)
          setRecordingStatus('uploaded')
          websocket.close()
          return
        }

        if (data.type === 'error') {
          setRecordingStatus('error')
          setRecordingError(data.detail ?? 'Live transcription failed')
          websocket.close()
        }
      }

      await new Promise<void>((resolve, reject) => {
        websocket.onopen = () => resolve()
        websocket.onerror = () => reject(new Error('Live transcription socket failed'))
      })
      websocket.onerror = () => {
        setRecordingStatus('error')
        setRecordingError('Live transcription socket failed')
      }

      const mimeType = getPreferredMimeType()
      const mediaRecorder = new MediaRecorder(
        stream,
        mimeType ? { mimeType } : undefined,
      )

      streamRef.current = stream
      mediaRecorderRef.current = mediaRecorder

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0 && websocket.readyState === WebSocket.OPEN) {
          websocket.send(event.data)
        }
      }

      mediaRecorder.onstop = () => {
        stopTimer()
        stopStream()

        if (websocket.readyState === WebSocket.OPEN) {
          setRecordingStatus('uploading')
          websocket.send(JSON.stringify({ type: 'stop' }))
        }
      }

      mediaRecorder.start(250)
      startTimer()
      setRecordingStatus('recording')
    } catch (error) {
      stopTimer()
      stopStream()
      websocketRef.current?.close()
      setRecordingStatus('error')
      setRecordingError(
        error instanceof Error
          ? error.message
          : 'Microphone permission was denied',
      )
    }
  }

  function stopRecording() {
    const mediaRecorder = mediaRecorderRef.current

    if (mediaRecorder?.state === 'recording') {
      mediaRecorder.stop()
    }
  }

  return (
    <main className="app-shell">
      <section className="intro-panel">
        <div className="eyebrow">Phase 7</div>
        <h1>Record your selected sentence</h1>
        <p>
          Choose a prompt, allow microphone access, and stream speech for live
          transcription before strict accuracy, fluency, and pronunciation
          scoring.
        </p>
      </section>

      <section className="status-bar" aria-label="System status">
        <span className={`status-dot ${apiStatus}`} aria-hidden="true" />
        <span>
          {apiStatus === 'checking' && 'Checking backend connection...'}
          {apiStatus === 'online' && `${prompts.length} prompts loaded`}
          {apiStatus === 'offline' && `Backend offline: ${errorMessage}`}
        </span>
      </section>

      <section className="practice-layout">
        <div className="prompt-browser">
          <div className="section-heading">
            <h2>Prompt list</h2>
            <span>{filteredPrompts.length} shown</span>
          </div>

          <div className="category-tabs" role="tablist" aria-label="Categories">
            {categories.map((category) => (
              <button
                aria-pressed={selectedCategory === category}
                className={selectedCategory === category ? 'active' : ''}
                disabled={isBusy}
                key={category}
                onClick={() => setSelectedCategory(category)}
                type="button"
              >
                {category}
              </button>
            ))}
          </div>

          <div className="prompt-list">
            {filteredPrompts.map((prompt) => (
              <button
                aria-pressed={selectedPromptId === prompt.id}
                className={`prompt-row ${
                  selectedPromptId === prompt.id ? 'selected' : ''
                }`}
                disabled={isBusy}
                key={prompt.id}
                onClick={() => setSelectedPromptId(prompt.id)}
                type="button"
              >
                <span className="prompt-meta">
                  {prompt.category} / {prompt.difficulty}
                </span>
                <strong>{prompt.text}</strong>
              </button>
            ))}
          </div>
        </div>

        <aside className="selected-panel" aria-label="Selected target sentence">
          <div className="section-heading">
            <h2>Target sentence</h2>
          </div>

          {selectedPrompt ? (
            <div className="target-card">
              <span className="prompt-meta">
                {selectedPrompt.category} / {selectedPrompt.difficulty}
              </span>
              <p>{selectedPrompt.text}</p>
            </div>
          ) : (
            <div className="empty-target">
              <p>Select a prompt to unlock recording.</p>
            </div>
          )}

          <div className="recording-panel" aria-live="polite">
            <div className="recording-meta">
              <span>Status</span>
              <strong>{recordingStatus}</strong>
            </div>
            <div className="recording-meta">
              <span>Elapsed</span>
              <strong>{elapsedSeconds}s</strong>
            </div>
          </div>

          {recordingStatus === 'recording' ? (
            <button className="stop-button" onClick={stopRecording} type="button">
              Stop and submit
            </button>
          ) : (
            <button
              className="record-button"
              disabled={!selectedPrompt || isBusy || apiStatus !== 'online'}
              onClick={startRecording}
              type="button"
            >
              {recordingStatus === 'requesting' && 'Requesting microphone...'}
              {recordingStatus === 'uploading' && 'Finalizing score...'}
              {recordingStatus !== 'requesting' &&
                recordingStatus !== 'uploading' &&
                'Start recording'}
            </button>
          )}

          {recordingError && <p className="error-message">{recordingError}</p>}

          {(recordingStatus === 'recording' ||
            recordingStatus === 'uploading' ||
            liveTranscript) && (
            <div className="live-transcript">
              <h3>Live transcript</h3>
              <p>{liveTranscript || 'Listening...'}</p>
            </div>
          )}

          {uploadResult && (
            <div className="upload-result">
              <h3>Strict accuracy</h3>
              <p>{uploadResult.message}</p>
              <div className="score-panel">
                <strong>{uploadResult.scores.accuracy}</strong>
                <span>/100</span>
              </div>
              <p>{uploadResult.explanation}</p>

              <div className="pronunciation-section">
                <h3>Pronunciation approximation</h3>
                <p>{uploadResult.pronunciation_explanation}</p>
                <div className="score-panel compact">
                  <strong>{uploadResult.scores.pronunciation}</strong>
                  <span>/100</span>
                </div>
                <div className="accuracy-metrics" aria-label="Pronunciation metrics">
                  <div>
                    <span>Phonetic match</span>
                    <strong>{uploadResult.metrics.phonetic_similarity}</strong>
                  </div>
                  <div>
                    <span>Word confidence</span>
                    <strong>
                      {uploadResult.metrics.average_word_confidence ?? '--'}
                    </strong>
                  </div>
                </div>
                <p className="limitation-note">
                  MVP limitation: this is an approximation based on transcript
                  phonetic distance and Deepgram confidence, not phoneme-level
                  pronunciation assessment.
                </p>
              </div>

              <div className="delivery-section">
                <h3>Fluency breakdown</h3>
                <p>{uploadResult.fluency_explanation}</p>

                <div className="score-grid" aria-label="Fluency scores">
                  <div>
                    <span>Fluency</span>
                    <strong>{uploadResult.scores.fluency}</strong>
                  </div>
                  <div>
                    <span>Pauses</span>
                    <strong>{uploadResult.scores.pause}</strong>
                  </div>
                  <div>
                    <span>Fillers</span>
                    <strong>{uploadResult.scores.filler}</strong>
                  </div>
                </div>

                <div className="accuracy-metrics" aria-label="Fluency metrics">
                  <div>
                    <span>Words / min</span>
                    <strong>
                      {uploadResult.metrics.words_per_minute ?? '--'}
                    </strong>
                  </div>
                  <div>
                    <span>Duration</span>
                    <strong>
                      {uploadResult.metrics.speaking_duration_seconds ?? '--'}s
                    </strong>
                  </div>
                  <div>
                    <span>Fillers</span>
                    <strong>{uploadResult.metrics.filler_count}</strong>
                  </div>
                  <div>
                    <span>Awkward pauses</span>
                    <strong>{uploadResult.metrics.awkward_pause_count}</strong>
                  </div>
                </div>

                {uploadResult.fillers.length > 0 && (
                  <div className="event-list" aria-label="Detected fillers">
                    {uploadResult.fillers.map((filler, index) => (
                      <span key={`${filler.word}-${index}`}>
                        {filler.word}
                        <small>{formatTimeRange(filler.start, filler.end)}</small>
                      </span>
                    ))}
                  </div>
                )}

                {uploadResult.pauses.length > 0 && (
                  <div className="event-list" aria-label="Detected pauses">
                    {uploadResult.pauses.map((pause, index) => (
                      <span className={pause.type} key={`${pause.type}-${index}`}>
                        {pause.type === 'awkward_pause'
                          ? 'Awkward pause'
                          : 'Mild hesitation'}
                        <small>
                          {pause.duration_seconds.toFixed(2)}s after{' '}
                          {pause.after_word}
                        </small>
                      </span>
                    ))}
                  </div>
                )}
              </div>

              <div className="accuracy-metrics" aria-label="Accuracy metrics">
                <div>
                  <span>Matches</span>
                  <strong>{uploadResult.metrics.match_count}</strong>
                </div>
                <div>
                  <span>Substitutions</span>
                  <strong>{uploadResult.metrics.substitution_count}</strong>
                </div>
                <div>
                  <span>Omissions</span>
                  <strong>{uploadResult.metrics.omission_count}</strong>
                </div>
                <div>
                  <span>Insertions</span>
                  <strong>{uploadResult.metrics.insertion_count}</strong>
                </div>
              </div>

              <div className="word-feedback-list" aria-label="Word feedback">
                {uploadResult.word_feedback.map((item, index) => (
                  <span className={item.status} key={`${item.status}-${index}`}>
                    {item.target_word ?? `+ ${item.spoken_word}`}
                    {item.status === 'substitution' && (
                      <small>{item.spoken_word}</small>
                    )}
                  </span>
                ))}
              </div>

              <h3>Deepgram transcript</h3>
              <blockquote>
                {uploadResult.transcript || 'No speech detected in this audio.'}
              </blockquote>
              <dl>
                <div>
                  <dt>Model</dt>
                  <dd>{uploadResult.deepgram_model}</dd>
                </div>
                <div>
                  <dt>Confidence</dt>
                  <dd>
                    {uploadResult.confidence === null
                      ? 'Not available'
                      : `${Math.round(uploadResult.confidence * 100)}%`}
                  </dd>
                </div>
                <div>
                  <dt>Audio</dt>
                  <dd>
                    {uploadResult.content_type}, {uploadResult.size_bytes} bytes
                  </dd>
                </div>
              </dl>

              {uploadResult.words.length > 0 && (
                <div className="word-timing-list" aria-label="Word timings">
                  {uploadResult.words.map((word, index) => (
                    <span key={`${word.word}-${index}`}>
                      {word.punctuated_word ?? word.word}
                      <small>
                        {word.start?.toFixed(2) ?? '--'}-
                        {word.end?.toFixed(2) ?? '--'}s
                      </small>
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </aside>
      </section>
    </main>
  )
}

function formatTimeRange(start: number | null, end: number | null) {
  if (start === null || end === null) {
    return '--'
  }

  return `${start.toFixed(2)}-${end.toFixed(2)}s`
}

export default App
