import { useStaffSettingsQuery } from '../queries/users'

function applyPhoneRegex(phone: string, pattern: string): string {
  if (!phone || !pattern) return phone
  try {
    const m = new RegExp(pattern).exec(phone)
    if (m) return m[1] ?? m[0]
  } catch {
  }
  return phone
}

export function usePhoneFormat() {
  const { data } = useStaffSettingsQuery()

  function formatPhone(phone: string | null | undefined): string {
    if (!phone) return ''
    return applyPhoneRegex(phone, data.value?.phone_extract_regex ?? '')
  }

  return { formatPhone }
}
