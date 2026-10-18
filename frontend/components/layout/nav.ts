import type { LucideIcon } from 'lucide-react'
import { ChartLine, FlaskConical, FolderGit2, GitCompareArrows, Search, TriangleAlert, Workflow } from 'lucide-react'

export interface NavItem { href: string; label: string; icon: LucideIcon; hint: string; crumb?: string; title?: string }

export const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: 'Analyze',
    items: [
      { href: '/', label: 'Overview', icon: ChartLine, hint: 'Graph health, criticality and open incidents', crumb: 'Main Dashboard' },
      { href: '/investigator', label: 'Investigator', icon: Search, hint: 'Ask the agent; every answer cites the graph', crumb: 'Root Cause Analysis' },
      { href: '/graph', label: 'Graph', icon: Workflow, hint: 'Explore services, edges and provenance', title: 'Dependency Graph' },
      { href: '/change-check', label: 'Change Check', icon: GitCompareArrows, hint: 'Blast radius of a diff before merge', crumb: 'Pre-merge impact' },
      { href: '/benchmark', label: 'Benchmark', icon: FlaskConical, hint: 'Held-out evaluation on this repository', crumb: 'Held-out evaluation' },
    ],
  },
  {
    group: 'Respond',
    items: [{ href: '/incidents', label: 'Incidents', icon: TriangleAlert, hint: 'Track, resolve and teach the graph', crumb: 'Incident log' }],
  },
  {
    group: 'System',
    items: [
      { href: '/repos', label: 'Repositories', icon: FolderGit2, hint: 'Connect, sync and switch GitHub repositories', crumb: 'Data sources' },
    ],
  },
]

export const ALL_PAGES = NAV.flatMap((g) => g.items)
