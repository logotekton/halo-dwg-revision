import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import ko from './ko.json'

// Single fixed locale for now (brief W1-01: "기본 언어 ko"). Locale switching
// / browser detection is out of scope until a second language exists.
void i18n.use(initReactI18next).init({
  resources: {
    ko: { translation: ko },
  },
  lng: 'ko',
  fallbackLng: 'ko',
  interpolation: { escapeValue: false },
})

export default i18n
