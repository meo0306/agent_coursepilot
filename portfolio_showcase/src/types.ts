export type NavItem = {
  id: string
  label: string
}

export type PositionCard = {
  id: string
  index: string
  label: string
  title: string
  description: string
  accent: 'problem' | 'decision' | 'result'
  isPlaceholder: boolean
}

export type ArchitectureStep = {
  id: string
  index: string
  eyebrow: string
  title: string
  description: string
  note: string
  isPlaceholder: boolean
}

export type CapabilityCard = {
  id: string
  product: 'CourseRAG' | 'CoursePilot' | 'Platform'
  index: string
  title: string
  description: string
  tags: string[]
  size: 'wide' | 'standard' | 'tall'
  tone: 'rag' | 'pilot' | 'neutral'
  isPlaceholder: boolean
}

export type WorkflowStep = {
  id: string
  index: string
  title: string
  subtitle: string
  description: string
}

export type WorkflowScenario = {
  id: 'lesson' | 'exam' | 'slides'
  label: string
  title: string
  output: string
  steps: WorkflowStep[]
  isPlaceholder: boolean
}

export type EvidenceMetric = {
  id: string
  value: number
  decimals?: number
  suffix: string
  label: string
  description: string
  status: 'complete' | 'failed' | 'next'
  isPlaceholder: boolean
}

export type DemoEvent = {
  id: string
  delay: number
  time: string
  label: string
  detail: string
  status: 'running' | 'waiting' | 'resumed' | 'verified' | 'exported'
}
