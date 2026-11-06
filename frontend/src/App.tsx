import { useCallback, useEffect, useRef, useState } from 'react'
import { api, message, post } from './api'
import { AuthDialog } from './AuthDialog'
import { RecommendationSettingsDialog } from './RecommendationSettingsDialog'
import { UnsavedSettingsDialog } from './UnsavedSettingsDialog'
import { PersonalSettings } from './PersonalSettings'
import { MealJournal } from './MealJournal'
import { PlannerView } from './PlannerView'
import { ConnectionNotice } from './ConnectionNotice'
import { GuestImport } from './GuestImport'
import { BrandMark } from './BrandArtwork'
import type { Feedback, PersonalSettings as Settings, User } from './types'

type View = 'planner' | 'settings' | 'meals'
const readView = (): View => {
  const value = window.location.hash.replace('#/', '')
  return value === 'settings' || value === 'meals' ? value : 'planner'
}

export function App() {
  const [view, setViewState] = useState<View>(readView)
  const [user, setUser] = useState<User | null>(null),
    userRef = useRef<User | null>(null)
  const [identityEpoch, setIdentityEpoch] = useState(0),
    identityVersion = useRef(0)
  const [authOpen, setAuthOpen] = useState(false),
    [authReady, setAuthReady] = useState(false)
  const [authLoading, setAuthLoading] = useState(true),
    [authError, setAuthError] = useState(''),
    [authAttempt, setAuthAttempt] = useState(0)
  const [personalLoading, setPersonalLoading] = useState(false),
    [personalReady, setPersonalReady] = useState(false)
  const [personalError, setPersonalError] = useState(''),
    [personalAttempt, setPersonalAttempt] = useState(0)
  const [settings, setSettings] = useState<Settings | null>(null),
    [feedback, setFeedback] = useState<Feedback[]>([])
  const settingsVersion = useRef(0),
    feedbackVersion = useRef(0)
  const authRequest = useRef<AbortController | null>(null),
    personalRequest = useRef<AbortController | null>(null)
  const [notice, setNotice] = useState(''),
    [error, setError] = useState('')
  const [firstSetup, setFirstSetup] = useState(false),
    [planSetupRequest, setPlanSetupRequest] = useState(0)
  const [resumePlanRequest, setResumePlanRequest] = useState(0),
    setupSequence = useRef(0)
  const resumePlannerDraft = useRef(false)
  const [dataRevision, setDataRevision] = useState(0),
    [importRevision, setImportRevision] = useState(0)
  const settingsDirty = useRef(false),
    [settingsUnsaved, setSettingsUnsaved] = useState(false)
  const settingsDirtyChanged = useCallback((dirty: boolean) => {
    settingsDirty.current = dirty
    setSettingsUnsaved(dirty)
  }, [])
  const [recommendSettingsOpen, setRecommendSettingsOpen] = useState(false)
  const recommendationDecision = useRef<{
    resolve: (allowed: boolean) => void
    version: number
    view: View
  } | null>(null)
  const [leaveSettings, setLeaveSettings] = useState<{ resolve: (leave: boolean) => void } | null>(
    null
  )
  const setView = (next: View) => {
    setViewState(next)
    setNotice('')
    if (window.location.hash !== `#/${next}`) window.location.hash = `/${next}`
    window.scrollTo({ top: 0, behavior: 'instant' })
  }
  useEffect(() => {
    const change = () => {
      setViewState(readView())
      window.scrollTo({ top: 0 })
    }
    window.addEventListener('hashchange', change)
    return () => window.removeEventListener('hashchange', change)
  }, [])
  const beforeRecommend = useCallback(async () => {
    if (!settingsDirty.current) return true
    if (recommendationDecision.current) return false
    return new Promise<boolean>((resolve) => {
      recommendationDecision.current = {
        resolve,
        version: identityVersion.current,
        view: readView()
      }
      setRecommendSettingsOpen(true)
    })
  }, [])
  const decideRecommendation = (decision: 'settings' | 'saved' | 'cancel') => {
    const waiting = recommendationDecision.current
    recommendationDecision.current = null
    setRecommendSettingsOpen(false)
    waiting?.resolve(
      decision === 'saved' &&
        waiting.version === identityVersion.current &&
        waiting.view === readView()
    )
    if (decision === 'settings') {
      resumePlannerDraft.current = true
      setView('settings')
    }
  }
  useEffect(
    () => () => {
      recommendationDecision.current?.resolve(false)
    },
    []
  )
  const canLeaveSettings = async () =>
    !settingsDirty.current ||
    (await new Promise<boolean>((resolve) => setLeaveSettings({ resolve })))
  const identify = (identity: User | null, closeAuth = true) => {
    recommendationDecision.current?.resolve(false)
    recommendationDecision.current = null
    setRecommendSettingsOpen(false)
    authRequest.current?.abort()
    personalRequest.current?.abort()
    identityVersion.current++
    setIdentityEpoch(identityVersion.current)
    userRef.current = identity
    setUser(identity)
    setAuthReady(true)
    setAuthLoading(false)
    setAuthError('')
    setPersonalError('')
    setPersonalLoading(false)
    setSettings(null)
    setFeedback([])
    setPersonalReady(false)
    setFirstSetup(false)
    setPlanSetupRequest(0)
    setResumePlanRequest(0)
    resumePlannerDraft.current = false
    if (closeAuth) setAuthOpen(false)
    setError('')
  }
  useEffect(() => {
    const controller = new AbortController(),
      version = identityVersion.current
    authRequest.current = controller
    setAuthLoading(true)
    setAuthError('')
    api<{ user: User | null }>('/auth/me', {}, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted && version === identityVersion.current)
          identify(value.user, false)
      })
      .catch((problem) => {
        if (!controller.signal.aborted) setAuthError(message(problem))
      })
      .finally(() => {
        if (!controller.signal.aborted) setAuthLoading(false)
      })
    return () => controller.abort()
  }, [authAttempt])
  useEffect(() => {
    if (!authReady) return
    const controller = new AbortController(),
      version = identityVersion.current
    const savedVersion = settingsVersion.current,
      ratingsVersion = feedbackVersion.current
    personalRequest.current = controller
    setPersonalLoading(true)
    setPersonalError('')
    Promise.all([
      api<Settings>('/preferences', {}, controller.signal),
      api<Feedback[]>('/feedback', {}, controller.signal)
    ])
      .then(([preferences, ratings]) => {
        if (controller.signal.aborted || version !== identityVersion.current) return
        if (savedVersion === settingsVersion.current) setSettings(preferences)
        if (ratingsVersion === feedbackVersion.current) setFeedback(ratings)
        setPersonalReady(true)
      })
      .catch((problem) => {
        if (!controller.signal.aborted && version === identityVersion.current)
          setPersonalError(message(problem))
      })
      .finally(() => {
        if (!controller.signal.aborted && version === identityVersion.current)
          setPersonalLoading(false)
      })
    return () => controller.abort()
  }, [authReady, identityEpoch, importRevision, personalAttempt])
  const saveSettings = async (value: Settings) => {
    const version = identityVersion.current
    const saved = await api<Settings>('/preferences', {
      method: 'PUT',
      body: JSON.stringify(value)
    })
    if (version === identityVersion.current) {
      settingsVersion.current++
      setSettings(saved)
    }
    return saved
  }
  const feedbackChanged = (value: Feedback | null, previousId?: string) => {
    if (identityEpoch !== identityVersion.current) return
    feedbackVersion.current++
    setFeedback((old) =>
      value
        ? [value, ...old.filter((item) => item.id !== value.id)]
        : old.filter((item) => item.id !== previousId)
    )
  }
  const continueToPlan = () => {
    if (identityEpoch !== identityVersion.current) return
    setFirstSetup(false)
    if (resumePlannerDraft.current) {
      resumePlannerDraft.current = false
      setResumePlanRequest(++setupSequence.current)
      setView('planner')
      setNotice('저장한 설정을 반영했어요. 이번 식단에서 따로 고른 메뉴와 조건은 유지해요.')
    } else {
      setPlanSetupRequest(++setupSequence.current)
      setView('planner')
    }
  }
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        본문으로 건너뛰기
      </a>
      <header className="topbar">
        <button className="brand" onClick={() => setView('planner')}>
          <BrandMark />
          <span>
            오늘 뭐 먹지?<small>내 입맛으로 채우는 하루</small>
          </span>
        </button>
        <nav aria-label="주요 메뉴">
          {(
            [
              ['planner', '오늘 식단'],
              ['meals', '식사 기록'],
              ['settings', '내 설정']
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              aria-current={view === key ? 'page' : undefined}
              className={view === key ? 'nav-active' : ''}
              onClick={() => setView(key)}
            >
              {label}
            </button>
          ))}
        </nav>
        <div className="account-actions">
          {user ? (
            <>
              <span className="username">{user.username}</span>
              <button
                className="text-button"
                onClick={async () => {
                  if (!(await canLeaveSettings())) return
                  try {
                    await post('/auth/logout', {})
                    identify(null)
                    setNotice('로그아웃했어요.')
                  } catch (problem) {
                    setError(message(problem))
                  }
                }}
              >
                로그아웃
              </button>
            </>
          ) : (
            <button
              className="login-button"
              disabled={authLoading || !authReady}
              onClick={async () => {
                if (await canLeaveSettings()) setAuthOpen(true)
              }}
            >
              {authLoading ? '확인 중…' : !authReady ? '연결 확인 필요' : '로그인'}
            </button>
          )}
        </div>
      </header>
      <main className="content" id="main-content" tabIndex={-1}>
        <ConnectionNotice
          key={`auth:${authAttempt}`}
          loading={authLoading}
          error={authError}
          loadingText="로그인 상태를 확인하고 있어요"
          errorTitle="로그인 상태를 확인하지 못했어요"
          retryLabel="로그인 상태 다시 확인"
          onRetry={() => setAuthAttempt((value) => value + 1)}
        />
        {authReady && (
          <ConnectionNotice
            key={`personal:${identityEpoch}:${personalAttempt}`}
            loading={personalLoading}
            error={personalError}
            loadingText="설정과 메뉴 평가를 불러오고 있어요"
            errorTitle="설정과 메뉴 평가를 불러오지 못했어요"
            retryLabel="설정 다시 불러오기"
            onRetry={() => setPersonalAttempt((value) => value + 1)}
          />
        )}
        {user && (
          <GuestImport
            key={user.id}
            accountId={user.id}
            inSettings={view === 'settings'}
            onImported={() => {
              setImportRevision((value) => value + 1)
              setNotice('')
            }}
          />
        )}
        {error && (
          <div className="notice error" role="alert">
            {error}
          </div>
        )}
        {notice && (
          <div className="notice success" role="status">
            {notice}
          </div>
        )}
        {personalReady && (
          <>
            <div hidden={view !== 'planner'}>
              <PlannerView
                key={`${user?.id ?? 'guest'}:${importRevision}`}
                account={Boolean(user)}
                settings={settings}
                feedback={feedback}
                onFeedback={feedbackChanged}
                revision={dataRevision}
                setupRequest={planSetupRequest}
                resumeRequest={resumePlanRequest}
                onSetupHandled={() => setPlanSetupRequest(0)}
                settingsUnsaved={settingsUnsaved}
                beforeRecommend={beforeRecommend}
                onJournal={() => setView('meals')}
                onSettings={() => {
                  resumePlannerDraft.current = true
                  setView('settings')
                }}
              />
            </div>
            <div hidden={view !== 'settings'}>
              <PersonalSettings
                key={user?.id ?? 'guest'}
                settings={settings}
                account={Boolean(user)}
                onSave={saveSettings}
                onDirtyChange={settingsDirtyChanged}
                firstSetup={firstSetup}
                onContinue={continueToPlan}
              />
            </div>
            {view === 'meals' && (
              <MealJournal
                key={`${user?.id ?? 'guest'}:${importRevision}`}
                account={Boolean(user)}
                feedback={feedback}
                onFeedback={feedbackChanged}
                onRecordsChange={() => setDataRevision((value) => value + 1)}
              />
            )}
          </>
        )}
      </main>
      <footer className="footer">
        <div>
          <span>오늘 뭐 먹지?</span>
          <p>내 입맛으로 채우는 하루.</p>
        </div>
        <p>
          영양은 공식 자료를 바탕으로 한 참고값이에요.
          <br />
          음식·업체·기준량에 따라 달라질 수 있어요.
        </p>
      </footer>
      {recommendSettingsOpen && <RecommendationSettingsDialog onDecision={decideRecommendation} />}
      {leaveSettings && (
        <UnsavedSettingsDialog
          onDecision={(leave) => {
            leaveSettings.resolve(leave)
            setLeaveSettings(null)
          }}
        />
      )}
      {authOpen && (
        <AuthDialog
          onClose={() => setAuthOpen(false)}
          onIdentity={(identity, mode) => {
            identify(identity)
            if (mode === 'register') {
              setFirstSetup(true)
              setView('settings')
            } else setNotice(`${identity.username}님, 반가워요.`)
          }}
        />
      )}
    </div>
  )
}
