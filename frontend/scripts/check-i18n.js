import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))

function flatten(obj, prefix = '') {
  return Object.entries(obj).reduce((acc, [key, value]) => {
    const fullKey = prefix ? `${prefix}.${key}` : key
    if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
      Object.assign(acc, flatten(value, fullKey))
    } else {
      acc[fullKey] = value
    }
    return acc
  }, {})
}

const ruPath = join(__dirname, '../src/i18n/ru.json')
const enPath = join(__dirname, '../src/i18n/en.json')

const ru = flatten(JSON.parse(readFileSync(ruPath, 'utf-8')))
const en = flatten(JSON.parse(readFileSync(enPath, 'utf-8')))

const ruKeys = new Set(Object.keys(ru))
const enKeys = new Set(Object.keys(en))

const missingInEn = [...ruKeys].filter(k => !enKeys.has(k))
const extraInEn   = [...enKeys].filter(k => !ruKeys.has(k))

let hasErrors = false

if (missingInEn.length > 0) {
  console.error('❌ Missing keys in en.json:')
  missingInEn.forEach(k => console.error('  -', k))
  hasErrors = true
}

if (extraInEn.length > 0) {
  console.warn('⚠️  Extra keys in en.json (not in ru.json):')
  extraInEn.forEach(k => console.warn('  -', k))
}

if (hasErrors) {
  process.exit(1)
} else {
  console.log(`✅ i18n OK: ${ruKeys.size} keys, all present in en.json`)
}
