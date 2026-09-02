import { useTranslation } from 'react-i18next'
import { AppHeader } from '../components/AppHeader'
import { StatusBar } from '../components/StatusBar'

export function App() {
  const { t } = useTranslation()

  return (
    <div className="flex h-screen flex-col bg-neutral-950 text-neutral-100">
      <AppHeader title={t('app.title')} />
      <main className="flex-1 overflow-hidden" aria-label={t('canvas.areaLabel')}>
        <div className="flex h-full items-center justify-center text-neutral-500">{t('canvas.placeholder')}</div>
      </main>
      <StatusBar />
    </div>
  )
}

export default App
