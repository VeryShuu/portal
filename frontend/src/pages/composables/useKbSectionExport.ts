import type { Ref } from 'vue'
import { exportSectionZip } from '../../api/kb'

export function useKbSectionExport(selectedSection: Ref<string | null>) {
  function onExportSection() {
    if (selectedSection.value) {
      exportSectionZip(selectedSection.value)
    }
  }

  return { onExportSection }
}
