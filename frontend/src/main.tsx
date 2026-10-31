import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'
import './personal.css'
import { App } from './App'
import './brand.css'
import './editorial.css'
import './service.css'
import './mealVisuals.css'
import './appPresentation.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode><App /></StrictMode>,
)
