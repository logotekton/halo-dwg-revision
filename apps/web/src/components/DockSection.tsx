interface DockSectionProps {
  title: string
  placeholder: string
}

/** One collapsible dock's named sub-section (e.g. left dock's "레이어"/"시트"). */
export function DockSection({ title, placeholder }: DockSectionProps) {
  return (
    <section className="border-b border-neutral-800 p-3 last:border-b-0">
      <h2 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-neutral-500">{title}</h2>
      <p className="text-neutral-600">{placeholder}</p>
    </section>
  )
}
