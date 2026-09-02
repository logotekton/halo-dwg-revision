interface AppHeaderProps {
  title: string
}

export function AppHeader({ title }: AppHeaderProps) {
  return (
    <header className="flex h-12 shrink-0 items-center border-b border-neutral-800 bg-neutral-900 px-4">
      <span className="text-sm font-semibold text-neutral-100">{title}</span>
    </header>
  )
}
