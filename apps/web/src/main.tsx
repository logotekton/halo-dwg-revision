import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './app/App'
import './i18n/i18n'
import './styles/index.css'

const container = document.getElementById('root')
if (!container) {
  throw new Error('root element (#root) not found')
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
