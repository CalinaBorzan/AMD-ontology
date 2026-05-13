<script setup>
import { nextTick, onMounted, onBeforeUnmount, ref, watch, computed } from 'vue'
import { Network, DataSet } from 'vis-network/standalone'
import { api } from '../api.js'

const container = ref(null)
const status = ref('loading')
const errorMessage = ref('')
const source = ref('backend')
const stats = ref({ classes: 0, instances: 0, triples: 0 })
const selectedNode = ref(null)

const filters = ref({
  showClasses: true,
  showInstances: true,
  showTriples: true,
})
const searchQuery = ref('')

let network = null
let nodesDS = null
let edgesDS = null
let allNodes = []
let allEdges = []
let ontologyRaw = null

const NODE_STYLES = {
  class: {
    color: {
      background: '#2b6cb0',
      border: '#1f5490',
      highlight: { background: '#1f5490', border: '#173f6e' },
      hover: { background: '#1f5490', border: '#173f6e' },
    },
    font: { color: '#ffffff', size: 14, face: 'Geist, sans-serif', vadjust: 0 },
    shape: 'box',
    margin: 12,
    borderWidth: 1,
    shapeProperties: { borderRadius: 6 },
  },
  instance: {
    color: {
      background: '#ffffff',
      border: '#d4dae3',
      highlight: { background: '#eaf2fb', border: '#2b6cb0' },
      hover: { background: '#eaf2fb', border: '#2b6cb0' },
    },
    font: { color: '#0b1320', size: 13, face: 'Geist, sans-serif' },
    shape: 'box',
    margin: 8,
    borderWidth: 1,
    shapeProperties: { borderRadius: 6 },
  },
}

const TYPE_EDGE = {
  color: { color: '#cbd5e1', highlight: '#6b7785', hover: '#6b7785' },
  dashes: [2, 3],
  font: { size: 10, color: '#97a0ad', face: 'Geist Mono, monospace', strokeWidth: 4, strokeColor: '#f7f8fb' },
  width: 1,
}
const SUBCLASS_EDGE = {
  color: { color: '#6b7785', highlight: '#0b1320', hover: '#0b1320' },
  font: { size: 10, color: '#3d4a5c', face: 'Geist Mono, monospace', strokeWidth: 4, strokeColor: '#f7f8fb' },
  width: 1.4,
}
const TRIPLE_EDGE = {
  color: { color: '#0ea5e9', highlight: '#2b6cb0', hover: '#2b6cb0' },
  font: { size: 11, color: '#0284c7', face: 'Geist Mono, monospace', strokeWidth: 4, strokeColor: '#f7f8fb', align: 'middle' },
  width: 1.5,
}

function buildGraph(ontology) {
  const nodes = new Map()
  const edges = []
  let edgeId = 0

  const ensureNode = (id, kind) => {
    if (nodes.has(id)) return
    nodes.set(id, { id, label: id, group: kind, ...NODE_STYLES[kind] })
  }

  const classes = ontology.classes || {}
  for (const className of Object.keys(classes)) ensureNode(className, 'class')

  for (const [className, def] of Object.entries(classes)) {
    for (const sub of def.subclasses || []) {
      ensureNode(sub, 'class')
      edges.push({
        id: `e${edgeId++}`,
        from: sub,
        to: className,
        label: 'subClassOf',
        kind: 'subclass',
        arrows: 'to',
        ...SUBCLASS_EDGE,
      })
    }
    for (const inst of def.instances || []) {
      ensureNode(inst, 'instance')
      edges.push({
        id: `e${edgeId++}`,
        from: inst,
        to: className,
        label: 'rdf:type',
        kind: 'type',
        arrows: 'to',
        ...TYPE_EDGE,
      })
    }
  }

  let tripleCount = 0
  const properties = ontology.properties || {}
  for (const examples of Object.values(properties)) {
    for (const [s, p, o] of examples.examples || []) {
      if (!nodes.has(s)) ensureNode(s, 'instance')
      if (!nodes.has(o)) ensureNode(o, 'instance')
      edges.push({
        id: `e${edgeId++}`,
        from: s,
        to: o,
        label: p,
        kind: 'triple',
        arrows: 'to',
        ...TRIPLE_EDGE,
      })
      tripleCount += 1
    }
  }

  const nodeArr = Array.from(nodes.values())
  stats.value = {
    classes: nodeArr.filter((n) => n.group === 'class').length,
    instances: nodeArr.filter((n) => n.group === 'instance').length,
    triples: tripleCount,
  }
  return { nodes: nodeArr, edges }
}

const visibleNodeIds = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  const ids = new Set()
  for (const n of allNodes) {
    if (n.group === 'class' && !filters.value.showClasses) continue
    if (n.group === 'instance' && !filters.value.showInstances) continue
    if (q && !n.label.toLowerCase().includes(q)) continue
    ids.add(n.id)
  }
  return ids
})

function applyView() {
  if (!nodesDS || !edgesDS) return
  const visible = visibleNodeIds.value

  nodesDS.clear()
  nodesDS.add(allNodes.filter((n) => visible.has(n.id)))

  edgesDS.clear()
  const filteredEdges = allEdges.filter((e) => {
    if (!visible.has(e.from) || !visible.has(e.to)) return false
    if (e.kind === 'triple' && !filters.value.showTriples) return false
    return true
  })
  edgesDS.add(filteredEdges)
}

watch([filters, searchQuery], applyView, { deep: true })

function inspectNode(nodeId) {
  if (!nodeId || !ontologyRaw) {
    selectedNode.value = null
    return
  }
  const classes = ontologyRaw.classes || {}
  const properties = ontologyRaw.properties || {}

  const isClass = !!classes[nodeId]
  const description = isClass ? classes[nodeId].description : null

  const parents = Object.entries(classes)
    .filter(([, def]) => (def.subclasses || []).includes(nodeId) || (def.instances || []).includes(nodeId))
    .map(([name]) => name)

  const children = isClass
    ? [...(classes[nodeId].subclasses || []), ...(classes[nodeId].instances || [])]
    : []

  const relations = []
  for (const [predName, predDef] of Object.entries(properties)) {
    for (const [s, p, o] of predDef.examples || []) {
      if (s === nodeId) relations.push({ direction: 'out', subject: s, predicate: p || predName, object: o })
      else if (o === nodeId) relations.push({ direction: 'in', subject: s, predicate: p || predName, object: o })
    }
  }

  selectedNode.value = {
    id: nodeId,
    kind: isClass ? 'class' : 'instance',
    description,
    parents,
    children,
    relations,
  }
}

async function fetchOntology() {
  try {
    return { data: await api.getOntology(), source: 'backend' }
  } catch (err) {
    const res = await fetch(`${import.meta.env.BASE_URL}mock_ontology.json`)
    if (!res.ok)
      throw new Error(`Backend unreachable and mock fetch failed: ${err.message}`, { cause: err })
    return { data: await res.json(), source: 'mock' }
  }
}

async function loadOntology() {
  try {
    status.value = 'loading'
    const { data, source: src } = await fetchOntology()
    source.value = src
    ontologyRaw = data
    const { nodes, edges } = buildGraph(data)
    allNodes = nodes
    allEdges = edges
    nodesDS = new DataSet(nodes)
    edgesDS = new DataSet(edges)

    await nextTick()
    if (!container.value) throw new Error('Graph container not mounted')

    network = new Network(
      container.value,
      { nodes: nodesDS, edges: edgesDS },
      {
        layout: { improvedLayout: true },
        physics: {
          solver: 'barnesHut',
          barnesHut: {
            gravitationalConstant: -14000,
            springLength: 160,
            springConstant: 0.04,
            damping: 0.5,
            avoidOverlap: 0.4,
          },
          stabilization: { iterations: 240 },
        },
        edges: {
          smooth: { type: 'continuous', roundness: 0.3 },
          arrows: { to: { scaleFactor: 0.55, type: 'arrow' } },
          selectionWidth: 2,
        },
        nodes: { borderWidth: 1, shadow: false },
        interaction: {
          hover: true,
          tooltipDelay: 150,
          zoomView: true,
          dragView: true,
        },
      },
    )

    network.on('click', (params) => {
      inspectNode(params.nodes.length > 0 ? params.nodes[0] : null)
    })

    network.once('stabilizationIterationsDone', () => network.fit())

    status.value = 'ready'
  } catch (err) {
    errorMessage.value = err.message || 'Failed to load ontology'
    status.value = 'error'
  }
}

function fitGraph() {
  if (network) network.fit({ animation: { duration: 480, easingFunction: 'easeInOutQuad' } })
}

async function reload() {
  if (network) {
    network.destroy()
    network = null
  }
  nodesDS = null
  edgesDS = null
  selectedNode.value = null
  await loadOntology()
}

onMounted(loadOntology)

onBeforeUnmount(() => {
  if (network) {
    network.destroy()
    network = null
  }
})
</script>

<template>
  <section class="atlas">
    <aside class="sidebar">
      <header class="sb-head">
        <span class="kicker">04 · Atlas</span>
        <h2>Ontology graph</h2>
      </header>

      <div class="src-row" :class="`src-${source}`">
        <span class="src-dot" />
        {{ source === 'backend' ? 'Live from backend' : 'Bundled mock data' }}
      </div>

      <div class="stats">
        <div>
          <div class="stat-num">{{ stats.classes }}</div>
          <div class="stat-lbl">Classes</div>
        </div>
        <div>
          <div class="stat-num">{{ stats.instances }}</div>
          <div class="stat-lbl">Instances</div>
        </div>
        <div>
          <div class="stat-num">{{ stats.triples }}</div>
          <div class="stat-lbl">Triples</div>
        </div>
      </div>

      <div class="block">
        <span class="block-title">Filters</span>
        <label class="flag">
          <input v-model="filters.showClasses" type="checkbox" />
          <span class="dot dot-class" />
          <span>Classes</span>
        </label>
        <label class="flag">
          <input v-model="filters.showInstances" type="checkbox" />
          <span class="dot dot-instance" />
          <span>Instances</span>
        </label>
        <label class="flag">
          <input v-model="filters.showTriples" type="checkbox" />
          <span class="dot dot-triple" />
          <span>Triple relations</span>
        </label>
      </div>

      <div class="block">
        <span class="block-title">Search</span>
        <div class="search-wrap">
          <svg class="search-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="7" cy="7" r="5" />
            <path d="M11 11l3 3" />
          </svg>
          <input v-model="searchQuery" type="search" placeholder="Filter nodes…" />
          <button v-if="searchQuery" class="clear" @click="searchQuery = ''" aria-label="Clear">×</button>
        </div>
      </div>

      <div class="actions">
        <button class="btn primary" :disabled="status !== 'ready'" @click="fitGraph">
          Fit to view
        </button>
        <button class="btn ghost" @click="reload">Reload</button>
      </div>

      <div v-if="selectedNode" class="inspector">
        <header class="inspector-head">
          <span :class="['type-tag', selectedNode.kind]">{{ selectedNode.kind }}</span>
          <button class="close" @click="selectedNode = null" aria-label="Close">×</button>
        </header>
        <h3 class="node-name">{{ selectedNode.id }}</h3>
        <p v-if="selectedNode.description" class="node-desc">{{ selectedNode.description }}</p>

        <div v-if="selectedNode.parents.length" class="rel-block">
          <span class="rel-lbl">Parent of</span>
          <div class="rel-chips">
            <span v-for="p in selectedNode.parents" :key="p" class="chip">{{ p }}</span>
          </div>
        </div>

        <div v-if="selectedNode.children.length" class="rel-block">
          <span class="rel-lbl">Contains ({{ selectedNode.children.length }})</span>
          <div class="rel-chips">
            <span v-for="c in selectedNode.children" :key="c" class="chip">{{ c }}</span>
          </div>
        </div>

        <div v-if="selectedNode.relations.length" class="rel-block">
          <span class="rel-lbl">Relations ({{ selectedNode.relations.length }})</span>
          <ul class="rel-list">
            <li v-for="(r, i) in selectedNode.relations" :key="i">
              <span class="rel-side">{{ r.direction === 'out' ? r.subject : r.subject }}</span>
              <span class="rel-pred">{{ r.predicate }}</span>
              <span class="rel-side">{{ r.object }}</span>
            </li>
          </ul>
        </div>
      </div>
    </aside>

    <div class="canvas">
      <div v-if="status === 'loading'" class="state">
        <span class="spinner" />
        Loading ontology…
      </div>
      <div v-else-if="status === 'error'" class="state error">
        <span class="error-icon">!</span>
        {{ errorMessage }}
      </div>
      <div ref="container" class="network" />
      <div class="overlay-hint">
        <span>drag · scroll to zoom · click nodes</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.atlas {
  display: grid;
  grid-template-columns: 320px 1fr;
  height: 100%;
  min-height: calc(100vh - var(--header-h));
  background: var(--bg);
}

.sidebar {
  background: var(--surface);
  border-right: 1px solid var(--border);
  padding: var(--s-5);
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
  overflow-y: auto;
}

.sb-head {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
}

.kicker {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--brand);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-weight: 500;
}

.sb-head h2 {
  font-size: var(--t-xl);
  font-weight: 600;
  letter-spacing: -0.02em;
  color: var(--text);
}

.src-row {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  padding: 6px var(--s-3);
  border-radius: var(--r-pill);
  font-size: 12px;
  font-weight: 500;
  width: fit-content;
}

.src-row.src-backend {
  background: var(--success-soft);
  color: var(--success);
  border: 1px solid #c5ecd0;
}

.src-row.src-mock {
  background: var(--warning-soft);
  color: var(--warning);
  border: 1px solid #fad8a3;
}

.src-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  animation: pulse 2s var(--ease) infinite;
}

.stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--s-3);
  padding: var(--s-3);
  background: var(--bg-tint);
  border-radius: var(--r-md);
}

.stats > div {
  display: flex;
  flex-direction: column;
  gap: 2px;
  text-align: center;
}

.stat-num {
  font-family: var(--font-mono);
  font-size: var(--t-lg);
  font-weight: 500;
  color: var(--text);
  letter-spacing: -0.02em;
}

.stat-lbl {
  font-size: 11px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.block {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.block-title {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  font-weight: 600;
}

.flag {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  padding: 6px var(--s-2);
  border-radius: var(--r-sm);
  cursor: pointer;
  font-size: var(--t-sm);
  color: var(--text);
  transition: background var(--speed) var(--ease);
}

.flag:hover {
  background: var(--bg-tint);
}

.flag input {
  accent-color: var(--brand);
  width: 14px;
  height: 14px;
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  flex-shrink: 0;
}

.dot-class {
  background: var(--brand);
}

.dot-instance {
  background: white;
  border: 1px solid var(--border-strong);
}

.dot-triple {
  background: var(--accent);
  border-radius: var(--r-pill);
  height: 2px;
  width: 14px;
}

.search-wrap {
  position: relative;
  display: flex;
  align-items: center;
}

.search-icon {
  position: absolute;
  left: var(--s-3);
  color: var(--text-muted);
  pointer-events: none;
}

.search-wrap input {
  width: 100%;
  padding: var(--s-2) var(--s-6) var(--s-2) var(--s-7);
  font-family: var(--font);
  font-size: var(--t-sm);
  color: var(--text);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  outline: none;
  transition: border-color var(--speed) var(--ease), box-shadow var(--speed) var(--ease);
}

.search-wrap input:focus {
  border-color: var(--border-focus);
  box-shadow: var(--shadow-focus);
  background: var(--surface);
}

.clear {
  position: absolute;
  right: var(--s-2);
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  color: var(--text-muted);
  background: var(--bg-tint);
  font-size: 16px;
  line-height: 1;
}

.clear:hover {
  color: var(--text);
  background: var(--border);
}

.actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--s-2);
}

.btn {
  padding: var(--s-2) var(--s-3);
  border-radius: var(--r-sm);
  font-size: var(--t-sm);
  font-weight: 500;
  transition: background var(--speed) var(--ease), color var(--speed) var(--ease), border-color var(--speed) var(--ease);
}

.btn.primary {
  background: var(--brand);
  color: white;
}

.btn.primary:hover:not(:disabled) {
  background: var(--brand-hover);
}

.btn.ghost {
  background: var(--surface);
  border: 1px solid var(--border);
  color: var(--text-soft);
}

.btn.ghost:hover {
  border-color: var(--border-strong);
  color: var(--text);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.inspector {
  margin-top: auto;
  padding: var(--s-4);
  background: var(--bg-tint);
  border-radius: var(--r-md);
  border: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  animation: fade-up 240ms var(--ease) both;
}

.inspector-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.type-tag {
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 2px var(--s-2);
  border-radius: var(--r-sm);
}

.type-tag.class {
  background: var(--brand);
  color: white;
}

.type-tag.instance {
  background: var(--surface);
  color: var(--text);
  border: 1px solid var(--border);
}

.close {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  color: var(--text-muted);
  font-size: 18px;
  line-height: 1;
}

.close:hover {
  background: var(--surface);
  color: var(--text);
}

.node-name {
  font-size: var(--t-md);
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text);
  word-break: break-word;
}

.node-desc {
  font-size: var(--t-sm);
  color: var(--text-soft);
  line-height: 1.5;
}

.rel-block {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.rel-lbl {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  font-weight: 600;
}

.rel-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.chip {
  padding: 2px var(--s-2);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  font-size: 12px;
  color: var(--text);
  font-family: var(--font-mono);
}

.rel-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
}

.rel-list li {
  display: flex;
  gap: 6px;
  font-size: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.rel-side {
  font-family: var(--font-mono);
  color: var(--text);
}

.rel-pred {
  color: var(--accent);
  font-family: var(--font-mono);
  font-size: 11px;
  background: var(--accent-soft);
  padding: 1px 6px;
  border-radius: var(--r-sm);
}

.canvas {
  position: relative;
  height: 100%;
  min-height: calc(100vh - var(--header-h));
  background:
    radial-gradient(circle at 20% 20%, rgba(43, 108, 176, 0.04), transparent 40%),
    linear-gradient(rgba(11, 19, 32, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(11, 19, 32, 0.04) 1px, transparent 1px);
  background-size: auto, 32px 32px, 32px 32px;
}

.network {
  position: absolute;
  inset: 0;
}

.state {
  position: absolute;
  top: var(--s-5);
  left: var(--s-5);
  display: inline-flex;
  align-items: center;
  gap: var(--s-3);
  padding: var(--s-3) var(--s-4);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-sm);
  font-size: var(--t-sm);
  color: var(--text-soft);
  z-index: 2;
}

.state.error {
  color: var(--danger);
  border-color: #f5c6cb;
}

.error-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--danger);
  color: white;
  font-size: 12px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.overlay-hint {
  position: absolute;
  right: var(--s-4);
  bottom: var(--s-4);
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
  background: var(--surface);
  padding: 4px var(--s-2);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  pointer-events: none;
}

.spinner {
  width: 14px;
  height: 14px;
  border: 1.5px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  display: inline-block;
  animation: spin 800ms linear infinite;
}

@media (max-width: 900px) {
  .atlas {
    grid-template-columns: 1fr;
  }
  .sidebar {
    border-right: none;
    border-bottom: 1px solid var(--border);
  }
}
</style>
