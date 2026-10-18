import { Fragment } from 'react'

interface Ctx { entity?: RegExp; onEntity?: (name: string) => void }

function entities(text: string, key: string, ctx: Ctx, bold = false): React.ReactNode {
  if (!ctx.entity || !ctx.onEntity) return bold ? <strong key={key} className="font-semibold">{text}</strong> : text
  return text.split(ctx.entity).map((part, i) =>
    i % 2 === 1 ? (
      <button
        key={`${key}-e${i}`}
        type="button"
        onClick={(e) => { e.stopPropagation(); ctx.onEntity!(part) }}
        className={`rounded px-0.5 font-mono text-[0.92em] text-primary underline decoration-primary/30 underline-offset-2 hover:bg-primary-soft hover:decoration-primary ${bold ? 'font-semibold' : ''}`}
      >
        {part}
      </button>
    ) : bold ? <strong key={`${key}-t${i}`} className="font-semibold">{part}</strong> : <Fragment key={`${key}-t${i}`}>{part}</Fragment>,
  )
}

function inline(text: string, key: string, ctx: Ctx = {}) {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g)
  return parts.map((p, i) => {
    const k = `${key}-${i}`
    if (p.startsWith('**') && p.endsWith('**')) return <Fragment key={k}>{entities(p.slice(2, -2), k, ctx, true)}</Fragment>
    if (p.startsWith('`') && p.endsWith('`')) return <code key={k} className="rounded bg-muted px-1 font-mono text-[0.9em]">{p.slice(1, -1)}</code>
    if (p.startsWith('*') && p.endsWith('*') && p.length > 2) return <em key={k}>{p.slice(1, -1)}</em>
    return <Fragment key={k}>{entities(p, k, ctx)}</Fragment>
  })
}

export function Markdown({ text, names, onEntity }: { text: string; names?: string[]; onEntity?: (name: string) => void }) {
  const ctx: Ctx = {
    onEntity,
    entity: names?.length ? new RegExp(`\\b(${[...names].sort((a, b) => b.length - a.length).map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})\\b`) : undefined,
  }
  const blocks: React.ReactNode[] = []
  let list: { ordered: boolean; items: string[] } | null = null
  const flush = () => {
    if (!list) return
    const L = list.ordered ? 'ol' : 'ul'
    blocks.push(
      <L key={blocks.length} className={`my-2 space-y-1 pl-5 ${list.ordered ? 'list-decimal' : 'list-disc'} marker:text-subtle-foreground`}>
        {list.items.map((it, i) => <li key={i}>{inline(it, `${blocks.length}-${i}`, ctx)}</li>)}
      </L>,
    )
    list = null
  }
  for (const raw of text.split('\n')) {
    const line = raw.trimEnd()
    const ul = /^\s*[-*] (.*)$/.exec(line)
    const ol = /^\s*\d+\. (.*)$/.exec(line)
    if (ul || ol) {
      const ordered = !!ol
      if (list && list.ordered !== ordered) flush()
      list ??= { ordered, items: [] }
      list.items.push((ul ?? ol)![1])
      continue
    }
    flush()
    if (line.trim()) blocks.push(<p key={blocks.length} className="my-1.5">{inline(line, String(blocks.length), ctx)}</p>)
  }
  flush()
  return <div className="text-sm leading-6">{blocks}</div>
}
