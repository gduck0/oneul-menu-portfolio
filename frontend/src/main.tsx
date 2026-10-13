import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'

function App() {
  return (
    <main className="welcome">
      <a className="brand" href="/" aria-label="오늘 뭐 먹지? 홈">
        <span aria-hidden="true">🐷</span> 오늘 뭐 먹지?
      </a>
      <section className="intro" aria-labelledby="welcome-title">
        <span className="mascot" aria-hidden="true">🐷</span>
        <p className="eyebrow">매일의 한 끼를 조금 더 가볍게</p>
        <h1 id="welcome-title">먹고 싶은 음식에서<br />시작하는 오늘의 한 끼</h1>
        <p className="description">음식의 영양 정보를 살펴보고,<br className="mobile-break" /> 나에게 맞는 대안을 골라 보세요.</p>
        <div className="coming-soon" role="status">음식 검색을 준비하고 있어요.</div>
      </section>
      <footer>오늘 뭐 먹지?</footer>
    </main>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode><App /></StrictMode>,
)
