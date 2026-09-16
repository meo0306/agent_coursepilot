import {
  type CSSProperties,
  type PointerEvent,
  type ReactNode,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import {
  architectureSteps,
  capabilityCards,
  demoEvents,
  evidenceMetrics,
  navItems,
  positionCards,
  workflowScenarios,
} from './content'
import type { EvidenceMetric, WorkflowScenario } from './types'
import styles from './styles/Showcase.module.css'

gsap.registerPlugin(ScrollTrigger)

const statusLabels: Record<EvidenceMetric['status'], string> = {
  complete: '已完成',
  failed: '未通过',
  next: '下一步',
}

function useReducedMotion() {
  const [reduced, setReduced] = useState(() =>
    typeof window === 'undefined'
      ? false
      : window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  )

  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setReduced(media.matches)
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])

  return reduced
}

function PlaceholderTag({ compact = false }: { compact?: boolean }) {
  return (
    <span className={compact ? styles.placeholderCompact : styles.placeholder}>
      示例内容
    </span>
  )
}

function ArrowIcon() {
  return <span aria-hidden="true">↗</span>
}

function SectionHeading({
  eyebrow,
  title,
  body,
  id,
  dark = false,
  align = 'left',
}: {
  eyebrow: string
  title: ReactNode
  body: string
  id?: string
  dark?: boolean
  align?: 'left' | 'center'
}) {
  return (
    <header
      className={`${styles.sectionHeading} ${dark ? styles.headingDark : ''} ${align === 'center' ? styles.headingCenter : ''}`}
      data-reveal
    >
      <p className={styles.eyebrow}>{eyebrow}</p>
      <h2 id={id}>{title}</h2>
      <p className={styles.sectionLead}>{body}</p>
    </header>
  )
}

function Navigation() {
  const [activeId, setActiveId] = useState('home')
  const [progress, setProgress] = useState(0)
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    const updateProgress = () => {
      const scrollable = document.documentElement.scrollHeight - window.innerHeight
      setProgress(scrollable > 0 ? Math.min(window.scrollY / scrollable, 1) : 0)
    }
    updateProgress()
    window.addEventListener('scroll', updateProgress, { passive: true })
    return () => window.removeEventListener('scroll', updateProgress)
  }, [])

  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return undefined
    const sections = navItems
      .map((item) => document.getElementById(item.id))
      .filter((section): section is HTMLElement => Boolean(section))
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0]
        if (visible) setActiveId(visible.target.id)
      },
      { rootMargin: '-30% 0px -55% 0px', threshold: [0, 0.2, 0.5] },
    )
    sections.forEach((section) => observer.observe(section))
    return () => observer.disconnect()
  }, [])

  return (
    <nav className={styles.nav} aria-label="主要导航">
      <div
        className={styles.navProgress}
        style={{ transform: `scaleX(${progress})` }}
        aria-hidden="true"
      />
      <a className={styles.brand} href="#home" onClick={() => setMenuOpen(false)}>
        <span className={styles.brandMark} aria-hidden="true">
          CP
        </span>
        <span>
          <strong>CoursePilot</strong>
          <small>Agent Course Studio</small>
        </span>
      </a>
      <button
        className={styles.menuButton}
        type="button"
        aria-expanded={menuOpen}
        aria-controls="site-navigation"
        onClick={() => setMenuOpen((value) => !value)}
      >
        <span className={styles.menuLines} aria-hidden="true" />
        <span className={styles.srOnly}>打开或关闭导航</span>
      </button>
      <div
        id="site-navigation"
        className={`${styles.navLinks} ${menuOpen ? styles.navLinksOpen : ''}`}
      >
        {navItems.map((item) => (
          <a
            key={item.id}
            href={`#${item.id}`}
            aria-current={activeId === item.id ? 'location' : undefined}
            onClick={() => setMenuOpen(false)}
          >
            <span>{item.label}</span>
          </a>
        ))}
      </div>
      <a className={styles.navCta} href="#demo">
        本地演示
        <ArrowIcon />
      </a>
    </nav>
  )
}

function HeroVisual() {
  return (
    <div className={styles.heroVisual} data-hero-visual aria-label="双核心系统抽象示意图">
      <div className={styles.heroGlow} />
      <div className={styles.heroOrbit} />
      <div className={`${styles.heroChip} ${styles.heroChipTop}`}>Stable Evidence</div>
      <div className={`${styles.heroChip} ${styles.heroChipBottom}`}>Typed Workflow</div>
      <div className={styles.systemTile}>
        <div className={styles.tileHeader}>
          <span>COURSE STUDIO / 01</span>
          <span className={styles.statusDot}>ENGINEERING MVP</span>
        </div>
        <div className={styles.tileCore}>
          <div className={`${styles.corePanel} ${styles.ragPanel}`}>
            <span className={styles.panelCode}>RAG</span>
            <div className={styles.panelSymbol} aria-hidden="true">
              <i />
              <i />
              <i />
            </div>
            <div>
              <strong>CourseRAG</strong>
              <small>Evidence infrastructure</small>
            </div>
          </div>
          <div className={styles.coreBridge} aria-hidden="true">
            <i />
            <span>HTTP</span>
            <i />
          </div>
          <div className={`${styles.corePanel} ${styles.pilotPanel}`}>
            <span className={styles.panelCode}>AGENT</span>
            <div className={styles.panelSymbol} aria-hidden="true">
              <b />
              <b />
              <b />
              <b />
            </div>
            <div>
              <strong>CoursePilot</strong>
              <small>Resumable workflow</small>
            </div>
          </div>
        </div>
        <div className={styles.tileFooter}>
          <span>Evidence</span>
          <span>Trace</span>
          <span>Artifact</span>
          <span>PostgreSQL</span>
        </div>
      </div>
    </div>
  )
}

function SpotlightCard({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  const handlePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect()
    event.currentTarget.style.setProperty('--spot-x', `${event.clientX - rect.left}px`)
    event.currentTarget.style.setProperty('--spot-y', `${event.clientY - rect.top}px`)
  }

  return (
    <div className={`${styles.spotlightCard} ${className}`} onPointerMove={handlePointerMove}>
      {children}
    </div>
  )
}

function ArchitectureDiagram() {
  return (
    <div className={styles.architectureDiagram} data-architecture-diagram>
      <div className={styles.diagramTopbar}>
        <div className={styles.windowDots} aria-hidden="true">
          <i />
          <i />
          <i />
        </div>
        <span>system.boundaries</span>
        <span>v1.0</span>
      </div>
      <div className={styles.diagramGrid}>
        <div className={styles.gridCoordinates} aria-hidden="true">
          <span>A1</span>
          <span>A2</span>
          <span>B1</span>
          <span>B2</span>
        </div>
        <div className={styles.monolithNode} data-arch-monolith>
          <span>STARTING POINT</span>
          <strong>Course Application</strong>
          <small>Retrieval · Workflow · State · Export</small>
          <div className={styles.monolithBars} aria-hidden="true">
            <i />
            <i />
            <i />
          </div>
        </div>
        <div className={styles.splitSystem} data-arch-split>
          <div className={`${styles.serviceNode} ${styles.serviceRag}`}>
            <span>KNOWLEDGE CORE</span>
            <strong>CourseRAG</strong>
            <small>Evidence & Retrieval</small>
          </div>
          <div className={styles.serviceLink} aria-hidden="true">
            <span>HTTP v1</span>
          </div>
          <div className={`${styles.serviceNode} ${styles.servicePilot}`}>
            <span>WORKFLOW CORE</span>
            <strong>CoursePilot</strong>
            <small>Agent & Artifact</small>
          </div>
        </div>
        <div className={styles.contractLayer} data-arch-contracts>
          <div className={styles.contractRail}>
            <span>Evidence</span>
            <i />
            <span>Trace</span>
            <i />
            <span>Artifact</span>
          </div>
          <div className={styles.databaseNode}>
            <span className={styles.databaseIcon} aria-hidden="true" />
            <div>
              <strong>PostgreSQL</strong>
              <small>Business source of truth</small>
            </div>
          </div>
        </div>
      </div>
      <div className={styles.diagramFooter}>
        <span>DOMAIN BOUNDARIES</span>
        <span>HTTP ONLY</span>
        <span>TWO SCHEMAS</span>
      </div>
    </div>
  )
}

function CountUp({
  value,
  decimals = 0,
  suffix,
}: {
  value: number
  decimals?: number
  suffix: string
}) {
  const reducedMotion = useReducedMotion()
  const [displayValue, setDisplayValue] = useState(0)
  const ref = useRef<HTMLSpanElement>(null)
  const hasRun = useRef(false)

  useEffect(() => {
    if (reducedMotion) return undefined
    const node = ref.current
    if (!node || typeof IntersectionObserver === 'undefined') return undefined
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting || hasRun.current) return
        hasRun.current = true
        const started = performance.now()
        const duration = 900
        const tick = (now: number) => {
          const progress = Math.min((now - started) / duration, 1)
          const eased = 1 - Math.pow(1 - progress, 3)
          const precision = 10 ** decimals
          setDisplayValue(Math.round(value * eased * precision) / precision)
          if (progress < 1) requestAnimationFrame(tick)
        }
        requestAnimationFrame(tick)
        observer.disconnect()
      },
      { threshold: 0.55 },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [decimals, reducedMotion, value])

  return (
    <span ref={ref}>
      {(reducedMotion || typeof IntersectionObserver === 'undefined' ? value : displayValue).toFixed(decimals)}
      <small>{suffix}</small>
    </span>
  )
}

function WorkflowStage({ scenario }: { scenario: WorkflowScenario }) {
  return (
    <div className={styles.workflowGrid}>
      <div className={styles.workflowSteps}>
        {scenario.steps.map((step, index) => (
          <article
            className={styles.workflowStep}
            data-workflow-step
            data-step-index={index}
            key={step.id}
          >
            <span>{step.index}</span>
            <div>
              <p>{step.subtitle}</p>
              <h3>{step.title}</h3>
              <small>{step.description}</small>
            </div>
          </article>
        ))}
      </div>
      <div className={styles.workflowMachine} data-workflow-machine>
        <div className={styles.machineHeader}>
          <span>workflow.trace</span>
          <span className={styles.machineStatus}>REFERENCE FLOW</span>
        </div>
        <div className={styles.machineBody}>
          <div className={styles.machineMeta}>
            <span>ACTIVE SCENARIO</span>
            <strong>{scenario.label}</strong>
          </div>
          <h3>{scenario.title}</h3>
          <div className={styles.traceRail} aria-hidden="true">
            <i className={styles.traceBase} />
            <i className={styles.traceFill} data-workflow-trace />
            {scenario.steps.map((step, index) => (
              <span
                key={step.id}
                className={styles.traceNode}
                data-workflow-node
                style={{ '--node-index': index } as CSSProperties}
              >
                {index + 1}
              </span>
            ))}
          </div>
          <div className={styles.machineOutput}>
            <span>OUTPUT ARTIFACT</span>
            <strong>{scenario.output}</strong>
            <small>versioned · editable · traceable</small>
          </div>
        </div>
        <div className={styles.machineFooter}>
          <span>stable thread</span>
          <span>PostgreSQL checkpoint</span>
        </div>
      </div>
    </div>
  )
}

function DemoConsole() {
  const [runId, setRunId] = useState(0)
  const [visibleCount, setVisibleCount] = useState(0)

  useEffect(() => {
    if (runId === 0) return undefined
    let elapsed = 0
    const timers = demoEvents.map((event, index) => {
      elapsed += event.delay
      return window.setTimeout(() => setVisibleCount(index + 1), elapsed)
    })
    return () => timers.forEach((timer) => window.clearTimeout(timer))
  }, [runId])

  const replay = () => {
    setVisibleCount(0)
    setRunId((value) => value + 1)
  }

  const completed = visibleCount === demoEvents.length

  return (
    <div className={styles.demoConsole}>
      <div className={styles.consoleBar}>
        <div className={styles.windowDots} aria-hidden="true">
          <i />
          <i />
          <i />
        </div>
        <span>courseportfolio / verified_journey.log</span>
        <span>recorded result</span>
      </div>
      <div className={styles.consoleBody}>
        <div className={styles.consoleIntro}>
          <p>VERIFIED LOCAL DEMO</p>
          <h3>一次已验证的双服务 Journey</h3>
          <span>
            回放 2026-08-26 的本地验证结果；页面本身不连接数据库、模型或外部 API。
          </span>
        </div>
        <div
          className={styles.consoleTimeline}
          aria-live="polite"
          aria-atomic="false"
          data-testid="demo-events"
        >
          {visibleCount === 0 && (
            <div className={styles.consoleEmpty}>
              <span className={styles.consolePrompt}>$</span>
              <span>点击下方按钮，回放已验证的工程链路</span>
              <i aria-hidden="true" />
            </div>
          )}
          {demoEvents.slice(0, visibleCount).map((event) => (
            <div className={styles.consoleEvent} key={`${runId}-${event.id}`}>
              <span className={styles.eventTime}>{event.time}</span>
              <span className={`${styles.eventStatus} ${styles[event.status]}`}>
                {event.status}
              </span>
              <div>
                <strong>{event.label}</strong>
                <small>{event.detail}</small>
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className={styles.consoleFooter}>
        <div>
          <span className={completed ? styles.completeLight : styles.readyLight} />
          {completed ? 'Replay completed' : runId > 0 ? 'Replay running' : 'Ready to replay'}
        </div>
        <button type="button" onClick={replay}>
          {runId > 0 ? '重新演示' : '开始演示'}
          <span aria-hidden="true">↻</span>
        </button>
      </div>
    </div>
  )
}

function useGsapExperience(
  rootRef: React.RefObject<HTMLDivElement | null>,
  reducedMotion: boolean,
) {
  useLayoutEffect(() => {
    const root = rootRef.current
    if (!root) return undefined

    if (reducedMotion) {
      root.querySelectorAll<HTMLElement>('[data-reveal]').forEach((element) => {
        element.style.opacity = '1'
        element.style.transform = 'none'
      })
      return undefined
    }

    const media = gsap.matchMedia()
    const context = gsap.context(() => {
      const heroTimeline = gsap.timeline({ defaults: { ease: 'power3.out' } })
      heroTimeline
        .from('[data-hero-kicker]', { opacity: 0, y: 18, duration: 0.6 })
        .from(
          '[data-hero-line]',
          { opacity: 0, yPercent: 110, rotate: 1.5, duration: 0.9, stagger: 0.1 },
          '-=0.25',
        )
        .from('[data-hero-summary]', { opacity: 0, y: 22, duration: 0.6 }, '-=0.4')
        .from('[data-hero-actions]', { opacity: 0, y: 18, duration: 0.5 }, '-=0.35')
        .from(
          '[data-hero-visual]',
          { opacity: 0, y: 30, rotateX: -5, scale: 0.97, duration: 1 },
          '-=0.8',
        )

      ScrollTrigger.batch('[data-reveal]', {
        start: 'top 88%',
        once: true,
        onEnter: (elements) =>
          gsap.fromTo(
            elements,
            { opacity: 0, y: 34 },
            { opacity: 1, y: 0, duration: 0.7, stagger: 0.08, ease: 'power3.out' },
          ),
      })

      media.add('(min-width: 960px)', () => {
        const archCards = gsap.utils.toArray<HTMLElement>('[data-architecture-copy]')
        const monolith = root.querySelector('[data-arch-monolith]')
        const split = root.querySelector('[data-arch-split]')
        const contracts = root.querySelector('[data-arch-contracts]')

        if (archCards.length === 3 && monolith && split && contracts) {
          gsap.set(archCards, { autoAlpha: 0, y: 28 })
          gsap.set(archCards[0], { autoAlpha: 1, y: 0 })
          gsap.set(split, { autoAlpha: 0, scale: 0.94 })
          gsap.set(contracts, { autoAlpha: 0, y: 20 })

          const architectureTimeline = gsap.timeline({
            scrollTrigger: {
              trigger: '[data-architecture-section]',
              start: 'top top',
              end: '+=220%',
              scrub: 0.8,
              pin: '[data-architecture-stage]',
              anticipatePin: 1,
            },
          })
          architectureTimeline
            .to({}, { duration: 0.3 })
            .to(archCards[0], { autoAlpha: 0, y: -24, duration: 0.22 })
            .to(monolith, { autoAlpha: 0, scale: 0.86, duration: 0.3 }, '<')
            .to(archCards[1], { autoAlpha: 1, y: 0, duration: 0.28 }, '<0.04')
            .to(split, { autoAlpha: 1, scale: 1, duration: 0.35 }, '<')
            .to({}, { duration: 0.35 })
            .to(archCards[1], { autoAlpha: 0, y: -24, duration: 0.22 })
            .to(archCards[2], { autoAlpha: 1, y: 0, duration: 0.28 }, '<0.04')
            .to(contracts, { autoAlpha: 1, y: 0, duration: 0.35 }, '<')
            .to({}, { duration: 0.4 })
        }

        const workflowSteps = gsap.utils.toArray<HTMLElement>('[data-workflow-step]')
        const workflowNodes = gsap.utils.toArray<HTMLElement>('[data-workflow-node]')
        const workflowTrace = root.querySelector('[data-workflow-trace]')
        if (workflowSteps.length && workflowTrace) {
          gsap.set(workflowSteps, { opacity: 0.32 })
          gsap.set(workflowSteps[0], { opacity: 1 })
          gsap.set(workflowNodes, { backgroundColor: '#19313a', color: '#8aa2a9' })
          gsap.set(workflowNodes[0], { backgroundColor: '#9debf0', color: '#061217' })
          gsap.set(workflowTrace, { scaleX: 0, transformOrigin: 'left center' })

          const workflowTimeline = gsap.timeline({
            scrollTrigger: {
              trigger: '[data-workflow-section]',
              start: 'top top',
              end: '+=230%',
              scrub: 0.7,
              pin: '[data-workflow-stage]',
              anticipatePin: 1,
            },
          })
          workflowSteps.forEach((step, index) => {
            if (index === 0) return
            workflowTimeline
              .to(workflowSteps[index - 1], { opacity: 0.32, duration: 0.15 })
              .to(step, { opacity: 1, duration: 0.2 }, '<')
              .to(
                workflowTrace,
                { scaleX: index / (workflowSteps.length - 1), duration: 0.24 },
                '<',
              )
              .to(
                workflowNodes[index],
                { backgroundColor: '#9debf0', color: '#061217', duration: 0.12 },
                '<',
              )
          })
          workflowTimeline.to(workflowTrace, { scaleX: 1, duration: 0.25 })
        }

        gsap.to('[data-hero-visual]', {
          yPercent: 8,
          ease: 'none',
          scrollTrigger: {
            trigger: '#home',
            start: 'top top',
            end: 'bottom top',
            scrub: 1,
          },
        })
      })
    }, root)

    return () => {
      media.revert()
      context.revert()
    }
  }, [reducedMotion, rootRef])
}

function App() {
  const rootRef = useRef<HTMLDivElement>(null)
  const reducedMotion = useReducedMotion()
  const [scenarioId, setScenarioId] = useState<WorkflowScenario['id']>('lesson')
  const scenario = useMemo(
    () => workflowScenarios.find((item) => item.id === scenarioId) ?? workflowScenarios[0],
    [scenarioId],
  )

  useGsapExperience(rootRef, reducedMotion)

  return (
    <div
      ref={rootRef}
      className={styles.site}
      data-reduced-motion={reducedMotion ? 'true' : 'false'}
    >
      <Navigation />
      <main id="main-content">
        <section id="home" className={styles.hero} aria-labelledby="hero-title">
          <div className={styles.heroAtmosphere} aria-hidden="true" />
          <div className={styles.heroGrid}>
            <div className={styles.heroCopy}>
              <div className={styles.heroKicker} data-hero-kicker>
                <span className={styles.liveDot} />
                Independent project · 2026.06—08
              </div>
              <h1 id="hero-title" className={styles.heroTitle}>
                <span data-hero-line>面向教师备课场景的</span>
                <span data-hero-line>
                  智能 <em>Agent</em> 平台
                </span>
              </h1>
              <p className={styles.heroSummary} data-hero-summary>
                从单体备课 Demo 演进为两个公开仓库：CourseRAG 提供稳定 Evidence 与版本化混合检索，
                CoursePilot 提供可暂停、可恢复、可校验的教学工作流。
              </p>
              <div className={styles.heroActions} data-hero-actions>
                <a className={styles.primaryButton} href="#architecture">
                  查看系统架构
                  <span aria-hidden="true">↓</span>
                </a>
                <a className={styles.textButton} href="#demo">
                  体验流程演示
                  <ArrowIcon />
                </a>
              </div>
              <div className={styles.heroMeta} data-hero-actions>
                <div>
                  <span>01</span>
                  <p>Evidence-first<br />knowledge core</p>
                </div>
                <div>
                  <span>02</span>
                  <p>Workflow-first<br />agent runtime</p>
                </div>
                <div>
                  <span>03</span>
                  <p>Human-in-the-loop<br />quality boundary</p>
                </div>
              </div>
            </div>
            <HeroVisual />
          </div>
          <a className={styles.scrollCue} href="#positioning" aria-label="继续浏览项目定位">
            <span>SCROLL TO EXPLORE</span>
            <i aria-hidden="true" />
          </a>
        </section>

        <section id="positioning" className={styles.positioning} aria-labelledby="position-title">
          <div className={styles.sectionFrame}>
            <div className={styles.positionIntro} data-reveal>
              <p className={styles.eyebrow}>01 · Product position</p>
              <h2 id="position-title">
                不是再加一个 AI 功能，
                <br />而是重新划定系统责任。
              </h2>
              <p>
                这次拆分先稳定 Port 与数据合同，再验证双进程边界，最后才物理拆仓，避免同时改写业务、网络和存储层。
              </p>
            </div>
            <div className={styles.positionCards}>
              {positionCards.map((card) => (
                <SpotlightCard
                  key={card.id}
                  className={`${styles.positionCard} ${styles[card.accent]}`}
                >
                  <article data-reveal>
                    <div className={styles.cardTopline}>
                      <span>{card.index}</span>
                      <span>{card.label}</span>
                    </div>
                    <h3>{card.title}</h3>
                    <p>{card.description}</p>
                    {card.isPlaceholder && <PlaceholderTag compact />}
                  </article>
                </SpotlightCard>
              ))}
            </div>
          </div>
        </section>

        <section
          id="architecture"
          className={styles.architectureSection}
          aria-labelledby="architecture-title"
          data-architecture-section
        >
          <div className={styles.architectureStage} data-architecture-stage>
            <div className={styles.architectureCopy}>
              <p className={`${styles.eyebrow} ${styles.eyebrowDark}`}>
                02 · Architecture evolution
              </p>
              <div className={styles.architectureCopyStack}>
                {architectureSteps.map((step, index) => (
                  <article
                    key={step.id}
                    data-architecture-copy
                    className={styles.architectureCopyCard}
                    aria-hidden={index > 0 ? undefined : undefined}
                  >
                    <div className={styles.archStepTop}>
                      <span>{step.index}</span>
                      <span>{step.eyebrow}</span>
                    </div>
                    <h2 id={index === 0 ? 'architecture-title' : undefined}>{step.title}</h2>
                    <p>{step.description}</p>
                    <div className={styles.archNote}>
                      <i />
                      <span>{step.note}</span>
                    </div>
                    {step.isPlaceholder && <PlaceholderTag compact />}
                  </article>
                ))}
              </div>
              <div className={styles.archPagination} aria-hidden="true">
                {architectureSteps.map((step) => (
                  <span key={step.id} />
                ))}
              </div>
            </div>
            <ArchitectureDiagram />
          </div>
        </section>

        <section id="capabilities" className={styles.capabilities} aria-labelledby="capability-title">
          <div className={styles.sectionFrame}>
            <SectionHeading
              id="capability-title"
              eyebrow="03 · Capability matrix"
              title={
                <>
                  两个核心，一组完整的
                  <br />教学成果生产能力。
                </>
              }
              body="下列能力均来自已完成的工程阶段；检索指标与内容质量结论在后文分别标注适用范围。"
            />
            <div className={styles.capabilityGrid}>
              {capabilityCards.map((card) => (
                <SpotlightCard
                  key={card.id}
                  className={`${styles.capabilityCard} ${styles[`size-${card.size}`]} ${styles[`tone-${card.tone}`]}`}
                >
                  <article data-reveal>
                    <div className={styles.capabilityHeader}>
                      <span>{card.index}</span>
                      <span>{card.product}</span>
                    </div>
                    <div className={styles.capabilityGlyph} aria-hidden="true">
                      <i />
                      <i />
                      <i />
                    </div>
                    <div className={styles.capabilityBody}>
                      <h3>{card.title}</h3>
                      <p>{card.description}</p>
                    </div>
                    <div className={styles.capabilityFooter}>
                      <div>
                        {card.tags.map((tag) => (
                          <span key={tag}>{tag}</span>
                        ))}
                      </div>
                      {card.isPlaceholder && <PlaceholderTag compact />}
                    </div>
                  </article>
                </SpotlightCard>
              ))}
            </div>
          </div>
        </section>

        <section
          id="workflow"
          className={styles.workflowSection}
          aria-labelledby="workflow-title"
          data-workflow-section
        >
          <div className={styles.workflowStage} data-workflow-stage>
            <div className={styles.workflowHeader}>
              <div>
                <p className={`${styles.eyebrow} ${styles.eyebrowDark}`}>04 · End-to-end workflow</p>
                <h2 id="workflow-title">
                  同一套可靠骨架，
                  <br />适配三类教学任务。
                </h2>
              </div>
              <div className={styles.workflowTabs} role="tablist" aria-label="选择教学任务">
                {workflowScenarios.map((item) => (
                  <button
                    type="button"
                    role="tab"
                    aria-selected={scenario.id === item.id}
                    aria-controls="workflow-panel"
                    id={`workflow-tab-${item.id}`}
                    key={item.id}
                    onClick={() => setScenarioId(item.id)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
            <div
              id="workflow-panel"
              role="tabpanel"
              aria-labelledby={`workflow-tab-${scenario.id}`}
            >
              <WorkflowStage scenario={scenario} />
            </div>
          </div>
        </section>

        <section id="evidence" className={styles.evidenceSection} aria-labelledby="evidence-title">
          <div className={styles.sectionFrame}>
            <SectionHeading
              id="evidence-title"
              eyebrow="05 · Engineering evidence"
              title={
                <>
                  成果不只靠描述，
                  <br />还要能看到验证边界。
                </>
              }
              body="数字来自现有评测与发布报告；Dev 指标、仓库测试和失败的正式质量 Gate 分开陈述。"
            />
            <div className={styles.metricGrid}>
              {evidenceMetrics.map((metric) => (
                <article className={styles.metricCard} key={metric.id} data-reveal>
                  <div className={styles.metricTopline}>
                    <span className={`${styles.metricStatus} ${styles[`status-${metric.status}`]}`}>
                      <i />
                      {statusLabels[metric.status]}
                    </span>
                    {metric.isPlaceholder && <PlaceholderTag compact />}
                  </div>
                  <strong className={styles.metricValue}>
                    <CountUp value={metric.value} decimals={metric.decimals} suffix={metric.suffix} />
                  </strong>
                  <h3>{metric.label}</h3>
                  <p>{metric.description}</p>
                </article>
              ))}
            </div>
            <div className={styles.evidenceNote} data-reveal>
              <div className={styles.noteIndex}>NOTE / 01</div>
              <div>
                <h3>工程成熟度 ≠ 内容质量结论</h3>
                <p>
                  P19 作品集发布 Gate 已通过，但 P18 正式内容质量 Gate 未通过。工程闭环与内容质量是两条不同结论，不能互相替代。
                </p>
              </div>
              <span className={styles.noteStamp}>HONEST BY DESIGN</span>
            </div>
          </div>
        </section>

        <section id="demo" className={styles.demoSection} aria-labelledby="demo-title">
          <div className={styles.sectionFrame}>
            <SectionHeading
              id="demo-title"
              dark
              eyebrow="06 · Interactive demo"
              title={
                <>
                  把已验证的本地链路
                  <br />变成可以亲手触发的回放。
                </>
              }
              body="点击回放 2026-08-26 已完成的 Docker Journey；它证明 HTTP 边界与任务闭环，不证明实时模型质量。"
            />
            <div data-reveal>
              <DemoConsole />
            </div>
          </div>
        </section>

        <section id="boundaries" className={styles.boundaries} aria-labelledby="boundary-title">
          <div className={styles.sectionFrame}>
            <SectionHeading
              id="boundary-title"
              eyebrow="07 · Ownership & boundaries"
              align="center"
              title={
                <>
                  最后，把项目讲清楚，
                  <br />也把边界讲清楚。
                </>
              }
              body="个人贡献、当前工程状态与未通过结论同时呈现；代码入口指向两个公开仓库。"
            />
            <div className={styles.boundaryGrid}>
              <article data-reveal>
                <span>01 / MY ROLE</span>
                <h3>我负责了什么</h3>
                <p>个人独立完成从单体到双服务的渐进拆分，并建设 Stable Evidence、混合检索、Typed Workflow、人工审批、局部修复与可信评测边界。</p>
              </article>
              <article data-reveal>
                <span>02 / CURRENT STATE</span>
                <h3>系统目前能做什么</h3>
                <p>两个公开仓库通过 HTTP 协作；本地 Docker 已验证双 API、双 Schema、远程 CourseRAG 调用和确定性 Lesson 任务完成，全程无付费 Provider 调用。</p>
              </article>
              <article data-reveal>
                <span>03 / LIMITATIONS</span>
                <h3>仍有哪些限制</h3>
                <p>P18 内容质量 Gate 未通过，Track B 有 7/8 live Journey 因缺少可恢复正式索引而阻塞；CourseRAG 指标只适用于课程特定小规模 Dev 集。</p>
              </article>
            </div>
            <div className={styles.finalCta} data-reveal>
              <div>
                <p>PUBLIC ENGINEERING PORTFOLIO</p>
                <h2>可运行、可审计、也如实保留失败结论。</h2>
              </div>
              <div className={styles.finalLinks}>
                <a href="#architecture">架构详解 <ArrowIcon /></a>
                <a href="#demo">演示脚本 <ArrowIcon /></a>
                <a href="https://github.com/meo0306/course-rag" target="_blank" rel="noreferrer">CourseRAG 仓库 <ArrowIcon /></a>
                <a href="https://github.com/meo0306/course-pilot" target="_blank" rel="noreferrer">CoursePilot 仓库 <ArrowIcon /></a>
              </div>
            </div>
          </div>
        </section>
      </main>
      <footer className={styles.footer}>
        <div className={styles.footerWordmark}>COURSEPILOT</div>
        <div className={styles.footerMeta}>
          <span>CourseRAG × CoursePilot</span>
          <span>Engineering MVP · evidence-scoped claims</span>
          <a href="#home">回到顶部 ↑</a>
        </div>
      </footer>
    </div>
  )
}

export default App
