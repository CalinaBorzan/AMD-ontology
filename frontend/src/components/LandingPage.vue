<script setup>
const emit = defineEmits(['navigate'])

const cards = [
  {
    id: 'manual',
    title: 'Manual extraction',
    body: 'Paste a single clinical abstract and inspect the entities and relations the model proposes.',
    cta: 'Open extractor',
    icon: 'doc',
    accent: 'brand',
  },
  {
    id: 'corpus',
    title: 'Corpus pipeline',
    body: 'Run the three-stage agentic pipeline across the full corpus, then approve or reject the validation agent\'s fixes.',
    cta: 'Configure run',
    icon: 'flow',
    accent: 'accent',
  },
  {
    id: 'graph',
    title: 'Ontology graph',
    body: 'Browse classes, instances and relations as an interactive figure with filters and search.',
    cta: 'Open viewer',
    icon: 'network',
    accent: 'success',
  },
]

const features = [
  { num: '03', label: 'Pipeline stages', detail: 'bootstrap · refine · extend' },
  { num: '04', label: 'LLM backbones', detail: 'Qwen, Llama 3, Llama 4' },
  { num: '01', label: 'Doctor in the loop', detail: 'every change reviewed' },
]

function go(id) {
  emit('navigate', id)
}
</script>

<template>
  <section class="page">
    <div class="hero">
      <div class="hero-bg" aria-hidden="true">
        <div class="blob blob-a" />
        <div class="blob blob-b" />
        <div class="grid-overlay" />
      </div>

      <div class="hero-inner">
        <span class="badge">
          <span class="badge-dot" />
          Bachelor's thesis · UTCluj · 2026
        </span>

        <h1 class="lede">
          An ontology of <span class="hl">age-related macular degeneration</span>,
          mined by agents and curated by a clinician.
        </h1>

        <p class="sub">
          Reads clinical trial abstracts. Proposes classes, instances and relations.
          Yields the floor to a human expert who keeps, edits or discards each one.
        </p>

        <div class="hero-actions">
          <button class="btn primary" @click="go('manual')">
            Try a single abstract
            <span class="arrow">→</span>
          </button>
          <button class="btn ghost" @click="go('graph')">View the graph</button>
        </div>

        <ul class="features">
          <li v-for="f in features" :key="f.label">
            <span class="f-num">{{ f.num }}</span>
            <div>
              <div class="f-label">{{ f.label }}</div>
              <div class="f-detail">{{ f.detail }}</div>
            </div>
          </li>
        </ul>
      </div>
    </div>

    <div class="contents">
      <div class="contents-head">
        <h2>Three points of entry</h2>
        <p>Pick the workflow that fits the question you're answering.</p>
      </div>

      <div class="cards">
        <article
          v-for="(card, i) in cards"
          :key="card.id"
          :class="['card', `accent-${card.accent}`]"
          tabindex="0"
          :aria-label="card.title"
          :style="{ animationDelay: `${i * 80}ms` }"
          @click="go(card.id)"
          @keydown.enter="go(card.id)"
          @keydown.space.prevent="go(card.id)"
        >
          <div class="card-icon" aria-hidden="true">
            <svg v-if="card.icon === 'doc'" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/>
              <path d="M14 3v6h6"/>
              <path d="M9 13h6M9 17h4"/>
            </svg>
            <svg v-else-if="card.icon === 'flow'" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="5" cy="6" r="2.5"/>
              <circle cx="12" cy="12" r="2.5"/>
              <circle cx="19" cy="6" r="2.5"/>
              <circle cx="12" cy="19" r="2.5"/>
              <path d="M7 7l3 4M14 7l3-1M12 14.5v2"/>
            </svg>
            <svg v-else viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="3"/>
              <circle cx="5" cy="5" r="2"/>
              <circle cx="19" cy="5" r="2"/>
              <circle cx="5" cy="19" r="2"/>
              <circle cx="19" cy="19" r="2"/>
              <path d="M7 6.5l3 3M17 6.5l-3 3M7 17.5l3-3M17 17.5l-3-3"/>
            </svg>
          </div>
          <h3>{{ card.title }}</h3>
          <p>{{ card.body }}</p>
          <span class="card-cta">
            {{ card.cta }} <span class="arrow">→</span>
          </span>
        </article>
      </div>
    </div>
  </section>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: var(--s-9);
  padding-bottom: var(--s-9);
  animation: fade-up 380ms var(--ease) both;
}

.hero {
  position: relative;
  overflow: hidden;
  padding: var(--s-9) var(--s-6) var(--s-8);
}

.hero-bg {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
}

.blob {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.5;
}

.blob-a {
  width: 520px;
  height: 520px;
  background: radial-gradient(circle, rgba(43, 108, 176, 0.35), transparent 70%);
  top: -180px;
  right: -120px;
}

.blob-b {
  width: 420px;
  height: 420px;
  background: radial-gradient(circle, rgba(14, 165, 233, 0.25), transparent 70%);
  bottom: -160px;
  left: -80px;
}

.grid-overlay {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(11, 19, 32, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(11, 19, 32, 0.04) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: radial-gradient(ellipse at center, black 30%, transparent 80%);
}

.hero-inner {
  position: relative;
  z-index: 1;
  max-width: var(--container);
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  align-self: flex-start;
  padding: 6px var(--s-3);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-pill);
  font-size: var(--t-xs);
  font-weight: 500;
  color: var(--text-muted);
  font-family: var(--font-mono);
  letter-spacing: 0.02em;
  box-shadow: var(--shadow-xs);
}

.badge-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--brand);
}

.lede {
  font-size: var(--t-hero);
  font-weight: 600;
  line-height: 1.04;
  letter-spacing: -0.03em;
  color: var(--text);
  max-width: 22ch;
}

.hl {
  background: linear-gradient(120deg, var(--brand) 0%, var(--accent) 100%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.sub {
  font-size: var(--t-md);
  color: var(--text-soft);
  max-width: 60ch;
  line-height: 1.6;
}

.hero-actions {
  display: flex;
  gap: var(--s-3);
  margin-top: var(--s-3);
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  padding: var(--s-3) var(--s-5);
  border-radius: var(--r-md);
  font-size: var(--t-sm);
  font-weight: 500;
  transition:
    background var(--speed) var(--ease),
    color var(--speed) var(--ease),
    transform var(--speed) var(--ease),
    box-shadow var(--speed) var(--ease),
    border-color var(--speed) var(--ease);
}

.btn .arrow {
  transition: transform var(--speed) var(--ease);
}

.btn:hover .arrow {
  transform: translateX(3px);
}

.btn.primary {
  background: var(--brand);
  color: white;
  box-shadow: var(--shadow-sm);
}

.btn.primary:hover {
  background: var(--brand-hover);
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}

.btn.ghost {
  background: var(--surface);
  border: 1px solid var(--border);
  color: var(--text);
}

.btn.ghost:hover {
  border-color: var(--brand);
  color: var(--brand);
}

.features {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--s-5);
  margin-top: var(--s-7);
  padding-top: var(--s-5);
  border-top: 1px solid var(--border);
  list-style: none;
}

.features li {
  display: flex;
  gap: var(--s-3);
  align-items: flex-start;
}

.f-num {
  font-family: var(--font-mono);
  font-size: var(--t-lg);
  font-weight: 500;
  color: var(--brand);
  letter-spacing: -0.02em;
  line-height: 1;
  padding-top: 2px;
}

.f-label {
  font-size: var(--t-sm);
  font-weight: 500;
  color: var(--text);
}

.f-detail {
  font-size: var(--t-sm);
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 12px;
}

.contents {
  max-width: var(--container);
  margin: 0 auto;
  padding: 0 var(--s-6);
  display: flex;
  flex-direction: column;
  gap: var(--s-6);
  width: 100%;
}

.contents-head h2 {
  font-size: var(--t-2xl);
  font-weight: 600;
  letter-spacing: -0.025em;
  color: var(--text);
}

.contents-head p {
  font-size: var(--t-md);
  color: var(--text-muted);
  margin-top: var(--s-2);
}

.cards {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--s-4);
}

.card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  padding: var(--s-5);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  cursor: pointer;
  outline: none;
  transition:
    transform var(--speed) var(--ease),
    box-shadow var(--speed) var(--ease),
    border-color var(--speed) var(--ease);
  opacity: 0;
  animation: fade-up 480ms var(--ease) both;
  overflow: hidden;
}

.card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: var(--card-accent, var(--brand));
  transform: scaleX(0);
  transform-origin: left;
  transition: transform var(--speed-slow) var(--ease);
}

.card:hover,
.card:focus-visible {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
  border-color: var(--card-accent, var(--brand));
}

.card:hover::before,
.card:focus-visible::before {
  transform: scaleX(1);
}

.card:hover .arrow,
.card:focus-visible .arrow {
  transform: translateX(4px);
}

.card.accent-brand { --card-accent: var(--brand); }
.card.accent-accent { --card-accent: var(--accent); }
.card.accent-success { --card-accent: var(--success); }

.card-icon {
  width: 40px;
  height: 40px;
  border-radius: var(--r-md);
  background: color-mix(in srgb, var(--card-accent) 10%, var(--surface));
  color: var(--card-accent);
  display: flex;
  align-items: center;
  justify-content: center;
}

.card h3 {
  font-size: var(--t-lg);
  font-weight: 600;
  letter-spacing: -0.015em;
  color: var(--text);
}

.card p {
  font-size: var(--t-sm);
  color: var(--text-muted);
  flex: 1;
  line-height: 1.55;
}

.card-cta {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  font-size: var(--t-sm);
  font-weight: 500;
  color: var(--card-accent, var(--brand));
  margin-top: var(--s-2);
}

.arrow {
  display: inline-block;
  transition: transform var(--speed) var(--ease);
}

@media (max-width: 900px) {
  .features {
    grid-template-columns: 1fr;
  }
  .cards {
    grid-template-columns: 1fr;
  }
}
</style>
