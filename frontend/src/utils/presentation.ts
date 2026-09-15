export function recordText(value: unknown, fallback = '未提供'): string {
  if (Array.isArray(value)) {
    const values = value.map((item) => recordText(item, '')).filter(Boolean)
    return values.length ? values.join('；') : fallback
  }
  if (typeof value === 'string') return value || fallback
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (!value || typeof value !== 'object') return fallback

  const record = value as Record<string, unknown>
  if (typeof record.name === 'string' && record.value != null) {
    return `${record.name}: ${recordText(record.value, '')}`
  }
  const candidateKeys = ['text', 'description', 'summary', 'question', 'name', 'title', 'reason']
  for (const key of candidateKeys) {
    const candidate = record[key]
    if (typeof candidate === 'string' && candidate) return candidate
  }
  const entries = Object.entries(record)
    .map(([key, entry]) => `${key}: ${recordText(entry, '')}`)
    .filter((entry) => !entry.endsWith(': '))
  return entries.length ? entries.join('；') : fallback
}

export function formatDateTime(value?: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}
