import type { GlobalThemeOverrides } from 'naive-ui'

const FONT = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"

const RED = '#d8262c'
const RED_HOVER = '#bd2026'
const RED_PRESSED = '#a11a1f'
const NAVY = '#0b2a4a'
const SKY = '#4a90c4'

// Danger — decoupled from brand red (mirrors tokens.css --color-danger ramp).
// Brand red stays on primary CTAs; destructive/error states use crimson.
const DANGER = '#be123c'
const DANGER_HOVER = '#9f1239'
const DANGER_PRESSED = '#881337'
const DANGER_DARK = '#f43f5e'
const DANGER_DARK_HOVER = '#fb7185'
const DANGER_DARK_PRESSED = '#e11d48'

export const lightThemeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: RED,
    primaryColorHover: RED_HOVER,
    primaryColorPressed: RED_PRESSED,
    primaryColorSuppl: RED_HOVER,
    infoColor: SKY,
    infoColorHover: '#5e9fce',
    infoColorPressed: '#3a82b9',
    infoColorSuppl: '#5e9fce',
    successColor: '#16a34a',
    successColorHover: '#15803d',
    warningColor: '#f59e0b',
    warningColorHover: '#d97706',
    errorColor: DANGER,
    errorColorHover: DANGER_HOVER,
    errorColorPressed: DANGER_PRESSED,
    errorColorSuppl: DANGER_HOVER,
    borderRadius: '8px',
    borderRadiusSmall: '6px',
    fontFamily: FONT,
    fontFamilyMono: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: '0.875rem',
    fontWeight: '400',
    fontWeightStrong: '700',
    bodyColor: '#f5f7fa',
    cardColor: '#ffffff',
    modalColor: '#ffffff',
    popoverColor: '#ffffff',
    textColorBase: '#0f172a',
    textColor1: '#0f172a',
    textColor2: '#334155',
    textColor3: '#64748b',
    placeholderColor: '#94a3b8',
    borderColor: '#e2e8f0',
    dividerColor: '#e2e8f0',
  },
  Button: {
    borderRadiusMedium: '8px',
    borderRadiusSmall: '6px',
    fontWeight: '600',
    fontWeightStrong: '700',
  },
  Card: {
    borderRadius: '12px',
    paddingMedium: '20px',
  },
  Menu: {
    itemTextColorActive: RED,
    itemIconColorActive: RED,
    itemTextColorActiveHover: RED_HOVER,
    itemIconColorActiveHover: RED_HOVER,
    itemColorActive: 'rgba(216, 38, 44, 0.08)',
    itemColorActiveHover: 'rgba(216, 38, 44, 0.12)',
  },
  Tag: {
    borderRadius: '6px',
  },
  Input: {
    borderRadius: '8px',
  },
  Layout: {
    siderColor: '#ffffff',
    headerColor: NAVY,
    headerTextColor: '#ffffff',
    color: '#f5f7fa',
  },
  Avatar: {
    color: '#143a66',
  },
  Tooltip: {
    color: NAVY,
  },
}

export const darkThemeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: RED,
    primaryColorHover: '#e7484e',
    primaryColorPressed: '#bd2026',
    primaryColorSuppl: '#e7484e',
    infoColor: '#6faed8',
    successColor: '#22c55e',
    warningColor: '#f59e0b',
    errorColor: DANGER_DARK,
    errorColorHover: DANGER_DARK_HOVER,
    errorColorPressed: DANGER_DARK_PRESSED,
    errorColorSuppl: DANGER_DARK_HOVER,
    borderRadius: '8px',
    borderRadiusSmall: '6px',
    fontFamily: FONT,
    fontSize: '0.875rem',
    fontWeight: '400',
    fontWeightStrong: '700',
    bodyColor: '#071426',
    cardColor: '#0f1e33',
    modalColor: '#0f1e33',
    popoverColor: '#0f1e33',
    textColorBase: '#e6eef8',
    textColor1: '#e6eef8',
    textColor2: '#cbd5e1',
    textColor3: '#94a9c4',
    placeholderColor: '#64809a',
    borderColor: '#1e3252',
    dividerColor: '#1e3252',
  },
  Button: {
    borderRadiusMedium: '8px',
    borderRadiusSmall: '6px',
    fontWeight: '600',
  },
  Card: {
    borderRadius: '12px',
    paddingMedium: '20px',
  },
  Menu: {
    itemTextColorActive: '#ff6b6f',
    itemIconColorActive: '#ff6b6f',
    itemColorActive: 'rgba(216, 38, 44, 0.16)',
    itemColorActiveHover: 'rgba(216, 38, 44, 0.22)',
  },
  Layout: {
    siderColor: '#0f1e33',
    headerColor: '#0b2a4a',
    headerTextColor: '#ffffff',
    color: '#071426',
  },
}
