<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../api.js'
import ModelSelector from './ModelSelector.vue'

const SAMPLE = `Age-related macular degeneration (AMD) is a leading cause of vision loss in patients over 50. Anti-VEGF therapies such as ranibizumab and aflibercept have transformed the management of neovascular (wet) AMD. Genetic studies have identified CFH, ARMS2 and HTRA1 as significant risk loci. Smoking and age remain the most consistent modifiable and non-modifiable risk factors respectively.`

// Stages: idle → extracting → reviewing → saving → saved | validating | validated | error
const stage = ref('idle')
const errorMessage = ref('')

const abstract = ref(SAMPLE)
const model = ref(null)
const result = ref(null)
const saveResult = ref(null)

const ontologyClasses = ref([])

const acceptedEntities = ref({})
const acceptedRelations = ref({})
const rejectedItems = ref([]) // [{ name, reason, picked, type }]

// Validation agent state (post-save)
const POLL_MS = 2000
const validateAfterSave = ref(true)
const validationId = ref(null)
const validationStatus = ref('idle') // idle | running | done | error
const validationError = ref('')
const validationLog = ref([])
const fixes = ref([])
const fixDecisions = ref({})
let validationTimer = null
let logOffset = 0

function pushValidationLogs(lines) {
  if (!Array.isArray(lines) || !lines.length) return
  validationLog.value = [...validationLog.value, ...lines]
}

const wordCount = computed(() => abstract.value.trim().split(/\s+/).filter(Boolean).length)

function entityKey(e) {
  return `${e.label}::${e.type || 'Unknown'}`
}

const groupedAccepted = computed(() => {
  if (!result.value?.entities) return []
  const map = new Map()
  for (const e of result.value.entities) {
    const k = e.type || 'Unknown'
    if (!map.has(k)) map.set(k, [])
    map.get(k).push(e)
  }
  return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b))
})

const checkedCount = computed(() => {
  const ents = Object.values(acceptedEntities.value).filter(Boolean).length
  const rels = Object.values(acceptedRelations.value).filter(Boolean).length
  const forced = rejectedItems.value.filter((r) => r.picked && r.type).length
  return { entities: ents + forced, relations: rels }
})

const canSave = computed(() => {
  const c = checkedCount.value
  return (c.entities > 0 || c.relations > 0) && stage.value === 'reviewing'
})

function parseRejected(line) {
  const idx = line.indexOf(':')
  if (idx === -1) return { name: line.trim(), reason: '' }
  return { name: line.slice(0, idx).trim(), reason: line.slice(idx + 1).trim() }
}

async function loadClasses() {
  try {
    const data = await api.getOntology()
    ontologyClasses.value = Object.keys(data.classes || {}).sort()
  } catch {
    ontologyClasses.value = []
  }
}

async function submit() {
  if (!abstract.value.trim() || !model.value) return
  stage.value = 'extracting'
  errorMessage.value = ''
  result.value = null
  saveResult.value = null

  try {
    const data = await api.extractAbstract({
      abstract: abstract.value,
      model: model.value.id,
      provider: model.value.provider,
    })
    result.value = data

    // Initialize all accepted as checked
    const ents = {}
    for (const e of data.entities || []) ents[entityKey(e)] = true
    acceptedEntities.value = ents

    const rels = {}
    for (let i = 0; i < (data.relations || []).length; i++) rels[i] = true
    acceptedRelations.value = rels

    rejectedItems.value = (data.rejected || []).map((line) => {
      const { name, reason } = parseRejected(line)
      return { name, reason, picked: false, type: ontologyClasses.value[0] || '' }
    })

    stage.value = 'reviewing'
  } catch (err) {
    errorMessage.value = err.response?.data?.detail || err.message || 'Extraction failed'
    stage.value = 'error'
  }
}

function toggleAll(group, value) {
  if (group === 'entities') {
    const next = {}
    for (const k of Object.keys(acceptedEntities.value)) next[k] = value
    acceptedEntities.value = next
  } else if (group === 'relations') {
    const next = {}
    for (const k of Object.keys(acceptedRelations.value)) next[k] = value
    acceptedRelations.value = next
  }
}

async function save() {
  if (!canSave.value) return
  stage.value = 'saving'
  errorMessage.value = ''

  const instances = []
  for (const e of result.value.entities || []) {
    if (acceptedEntities.value[entityKey(e)]) {
      instances.push({ name: e.label, type: e.type || 'Unknown' })
    }
  }
  for (const r of rejectedItems.value) {
    if (r.picked && r.type) instances.push({ name: r.name, type: r.type })
  }

  const triples = []
  for (let i = 0; i < (result.value.relations || []).length; i++) {
    if (acceptedRelations.value[i]) {
      const r = result.value.relations[i]
      triples.push({ subject: r.subject, predicate: r.predicate, object: r.object })
    }
  }

  try {
    saveResult.value = await api.batchAdd({ instances, triples })
    stage.value = 'saved'
    await loadClasses() // refresh in case new classes appeared
    if (validateAfterSave.value) {
      await runValidation()
    }
  } catch (err) {
    errorMessage.value = err.response?.data?.detail || err.message || 'Save failed'
    stage.value = 'error'
  }
}

function reset() {
  result.value = null
  saveResult.value = null
  acceptedEntities.value = {}
  acceptedRelations.value = {}
  rejectedItems.value = []
  errorMessage.value = ''
  stage.value = 'idle'
  validationId.value = null
  validationStatus.value = 'idle'
  validationError.value = ''
  fixes.value = []
  fixDecisions.value = {}
  if (validationTimer) clearTimeout(validationTimer)
  validationTimer = null
}

function loadSample() {
  abstract.value = SAMPLE
}

async function pollValidation() {
  if (!validationId.value) return
  try {
    const [state, logData] = await Promise.all([
      api.getRun(validationId.value).catch(() => null),
      api.getRunLogs(validationId.value, logOffset).catch(() => null),
    ])
    if (logData?.lines?.length) {
      pushValidationLogs(logData.lines)
      logOffset = logData.next_offset
    }
    if (state?.status === 'done' || state?.status === 'completed') {
      try {
        const data = await api.getFixes(validationId.value)
        fixes.value = Array.isArray(data) ? data : data.fixes || []
        pushValidationLogs([
          `✓ Validation complete: ${fixes.value.length} proposed fix${fixes.value.length === 1 ? '' : 'es'}.`,
        ])
      } catch (err) {
        fixes.value = []
        pushValidationLogs([`! Fixes fetch failed: ${err.message}`])
      }
      validationStatus.value = 'done'
      stage.value = 'validated'
      return
    }
    if (state?.status === 'error' || state?.status === 'failed') {
      validationStatus.value = 'error'
      validationError.value = state.error || 'Validation failed'
      pushValidationLogs([`✗ ${validationError.value}`])
      stage.value = 'saved'
      return
    }
    validationTimer = setTimeout(pollValidation, POLL_MS)
  } catch (err) {
    validationStatus.value = 'error'
    validationError.value = err.response?.data?.detail || err.message || 'Polling failed'
    pushValidationLogs([`✗ ${validationError.value}`])
    stage.value = 'saved'
  }
}

async function runValidation() {
  if (!model.value) return
  validationStatus.value = 'running'
  validationError.value = ''
  validationLog.value = []
  logOffset = 0
  fixes.value = []
  fixDecisions.value = {}
  stage.value = 'validating'
  pushValidationLogs([`▶ Starting validation agent (${model.value.id})…`])
  try {
    const res = await api.startValidation({
      model: model.value.id,
      provider: model.value.provider,
      max_passes: 1,
    })
    validationId.value = res.job_id
    pushValidationLogs([`▶ Validation job ${res.job_id} started. Polling for updates…`])
    pollValidation()
  } catch (err) {
    validationStatus.value = 'error'
    validationError.value = err.response?.data?.detail || err.message || 'Failed to start validation'
    pushValidationLogs([`✗ ${validationError.value}`])
    stage.value = 'saved'
  }
}

async function decideFix(fix, action) {
  const fixId = fix.fix_id ?? fix.id
  fixDecisions.value = { ...fixDecisions.value, [fixId]: 'pending' }
  try {
    await api.decideFix(validationId.value, fixId, action)
    fixDecisions.value = { ...fixDecisions.value, [fixId]: action }
  } catch (err) {
    fixDecisions.value = { ...fixDecisions.value, [fixId]: 'error' }
    validationError.value = err.response?.data?.detail || err.message || 'Decision failed'
  }
}

function fixSummary(fix) {
  if (fix.summary) return fix.summary
  if (fix.message) return fix.message
  if (fix.description) return fix.description
  if (fix.subject && fix.predicate && fix.object)
    return `${fix.subject} ${fix.predicate} ${fix.object}`
  return JSON.stringify(fix)
}

onMounted(loadClasses)

onBeforeUnmount(() => {
  if (validationTimer) clearTimeout(validationTimer)
})
</script>

<template>
  <section class="page">
    <header class="page-head">
      <span class="kicker">02 · Manual extraction</span>
      <h2>Read a single abstract.</h2>
      <p>
        Paste one paragraph of clinical prose. The model proposes entities and relations; you
        review them, optionally rescue any the extractor filtered out, and save the approved
        items into the ontology.
      </p>
    </header>

    <!-- progress rail -->
    <ol class="rail">
      <li :class="{ active: stage === 'idle' || stage === 'extracting', done: ['reviewing','saving','saved'].includes(stage) }">
        <span class="rail-num">1</span>
        <span class="rail-lbl">Compose</span>
      </li>
      <li :class="{ active: stage === 'reviewing' || stage === 'saving', done: ['saved','validating','validated'].includes(stage) }">
        <span class="rail-num">2</span>
        <span class="rail-lbl">Review</span>
      </li>
      <li :class="{ active: ['saved','validating','validated'].includes(stage) }">
        <span class="rail-num">3</span>
        <span class="rail-lbl">Save</span>
      </li>
    </ol>

    <div class="grid">
      <!-- LEFT: compose form (always visible, but disabled while reviewing) -->
      <form class="card compose" @submit.prevent="submit">
        <header class="card-head">
          <h3>Compose</h3>
          <button type="button" class="link" @click="loadSample">Load sample</button>
        </header>

        <div class="field">
          <label for="abstract" class="lbl">Abstract</label>
          <div class="textarea-wrap">
            <textarea
              id="abstract"
              v-model="abstract"
              :readonly="stage === 'reviewing' || stage === 'saving'"
              rows="14"
              placeholder="Paste an AMD abstract (150–300 words)…"
            />
            <span class="counter">{{ wordCount }} words</span>
          </div>
        </div>

        <ModelSelector v-model="model" label="Model" />

        <div class="actions">
          <button
            v-if="stage !== 'reviewing' && stage !== 'saving' && stage !== 'saved'"
            type="submit"
            class="btn primary"
            :disabled="!abstract.trim() || !model || stage === 'extracting'"
          >
            <span v-if="stage === 'extracting'" class="spinner" />
            {{ stage === 'extracting' ? 'Extracting…' : 'Preview extraction' }}
            <span v-if="stage !== 'extracting'" class="arrow">→</span>
          </button>
          <button
            v-else
            type="button"
            class="btn ghost"
            @click="reset"
          >
            Start over
          </button>
        </div>

        <p v-if="errorMessage" class="error">
          <span class="error-icon">!</span>
          {{ errorMessage }}
        </p>
      </form>

      <!-- RIGHT: result + review -->
      <div class="card result">
        <header class="card-head">
          <h3>{{ ['saved','validating','validated'].includes(stage) ? 'Saved to ontology' : 'Review &amp; approve' }}</h3>
          <span v-if="stage === 'reviewing'" class="meta-pill">
            {{ checkedCount.entities }} / {{ result?.entities?.length + rejectedItems.length }} entities
            · {{ checkedCount.relations }} / {{ result?.relations?.length || 0 }} relations
          </span>
        </header>

        <div v-if="stage === 'idle'" class="empty">
          Results will appear here. Nothing is saved until you approve.
        </div>

        <div v-else-if="stage === 'extracting'" class="empty loading">
          <span class="spinner big" />
          <span>Calling the model… 10–60 seconds depending on the backbone.</span>
        </div>

        <!-- REVIEW STAGE -->
        <template v-else-if="stage === 'reviewing' || stage === 'saving'">
          <p class="note">
            <span class="note-dot" />
            Nothing is saved to the ontology yet. Tick what to keep, then save.
          </p>

          <!-- Accepted entities -->
          <section class="block">
            <header class="block-head accept">
              <span class="block-title">
                <span class="accept-mark">✓</span>
                Extracted entities
              </span>
              <span class="block-count">{{ result.entities?.length || 0 }}</span>
              <div class="block-actions">
                <button type="button" class="micro" @click="toggleAll('entities', true)">All</button>
                <button type="button" class="micro" @click="toggleAll('entities', false)">None</button>
              </div>
            </header>
            <div v-if="!groupedAccepted.length" class="empty inline">No entities extracted.</div>
            <div v-for="[type, entities] in groupedAccepted" :key="type" class="entity-group">
              <span class="group-label">{{ type }}</span>
              <div class="rows">
                <label
                  v-for="e in entities"
                  :key="entityKey(e)"
                  class="row"
                  :class="{ unchecked: !acceptedEntities[entityKey(e)] }"
                >
                  <input
                    type="checkbox"
                    v-model="acceptedEntities[entityKey(e)]"
                  />
                  <span class="row-name">{{ e.label }}</span>
                  <span class="row-arrow">→</span>
                  <span class="row-type">{{ e.type }}</span>
                </label>
              </div>
            </div>
          </section>

          <!-- Rejected entities -->
          <section v-if="rejectedItems.length" class="block">
            <header class="block-head reject">
              <span class="block-title">
                <span class="reject-mark">⊘</span>
                Filtered out by extractor
              </span>
              <span class="block-count">{{ rejectedItems.length }}</span>
            </header>
            <p class="block-note">
              Rescue any of these by ticking the box and assigning a type.
            </p>
            <div class="rows">
              <label
                v-for="(r, i) in rejectedItems"
                :key="`${r.name}-${i}`"
                class="row rejected-row"
                :class="{ picked: r.picked }"
              >
                <input type="checkbox" v-model="r.picked" />
                <div class="rejected-info">
                  <span class="row-name mono">{{ r.name }}</span>
                  <span v-if="r.reason" class="row-reason">{{ r.reason }}</span>
                </div>
                <select
                  v-model="r.type"
                  class="type-select"
                  :disabled="!r.picked"
                  @click.stop
                >
                  <option v-for="c in ontologyClasses" :key="c" :value="c">{{ c }}</option>
                </select>
              </label>
            </div>
          </section>

          <!-- Relations -->
          <section class="block">
            <header class="block-head accept">
              <span class="block-title">
                <span class="accept-mark">✓</span>
                Relations
              </span>
              <span class="block-count">{{ result.relations?.length || 0 }}</span>
              <div v-if="result.relations?.length" class="block-actions">
                <button type="button" class="micro" @click="toggleAll('relations', true)">All</button>
                <button type="button" class="micro" @click="toggleAll('relations', false)">None</button>
              </div>
            </header>
            <div v-if="!result.relations?.length" class="empty inline">No relations extracted.</div>
            <div v-else class="rows">
              <label
                v-for="(r, i) in result.relations"
                :key="i"
                class="row triple-row"
                :class="{ unchecked: !acceptedRelations[i] }"
              >
                <input type="checkbox" v-model="acceptedRelations[i]" />
                <span class="triple-s">{{ r.subject }}</span>
                <span class="triple-p">{{ r.predicate }}</span>
                <span class="triple-o">{{ r.object }}</span>
              </label>
            </div>
          </section>

          <details v-if="result.raw_llm_output" class="raw">
            <summary>Raw model output</summary>
            <pre>{{ result.raw_llm_output }}</pre>
          </details>

          <!-- Validation opt-in -->
          <label class="validate-toggle">
            <input type="checkbox" v-model="validateAfterSave" :disabled="stage === 'saving'" />
            <div>
              <div class="validate-toggle-title">
                Run validation agent after save
                <span class="rec">recommended</span>
              </div>
              <div class="validate-toggle-body">
                A second LLM agent re-reads the ontology and proposes corrections you can approve
                or reject — like a peer review.
              </div>
            </div>
          </label>

          <!-- Sticky footer -->
          <footer class="approve-bar">
            <button type="button" class="btn ghost" @click="reset" :disabled="stage === 'saving'">
              Cancel
            </button>
            <button
              type="button"
              class="btn primary"
              :disabled="!canSave"
              @click="save"
            >
              <span v-if="stage === 'saving'" class="spinner" />
              <template v-if="stage === 'saving'">Saving…</template>
              <template v-else-if="validateAfterSave">
                Save {{ checkedCount.entities + checkedCount.relations }} &amp; validate
              </template>
              <template v-else>
                Save {{ checkedCount.entities + checkedCount.relations }} items
              </template>
              <span v-if="stage !== 'saving'" class="arrow">→</span>
            </button>
          </footer>
        </template>

        <!-- SAVED -->
        <template v-else-if="['saved', 'validating', 'validated'].includes(stage) && saveResult">
          <div class="saved-banner">
            <div class="saved-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <div>
              <h4>Ontology updated</h4>
              <p>
                Added <strong>{{ saveResult.instances_added.length }}</strong> instance{{ saveResult.instances_added.length === 1 ? '' : 's' }} and
                <strong>{{ saveResult.triples_added.length }}</strong> relation{{ saveResult.triples_added.length === 1 ? '' : 's' }}.
              </p>
            </div>
          </div>

          <div class="save-grid">
            <div class="save-col">
              <span class="save-lbl added">Added · {{ saveResult.instances_added.length }} instances</span>
              <ul v-if="saveResult.instances_added.length" class="save-list">
                <li v-for="x in saveResult.instances_added" :key="x" class="save-item added">{{ x }}</li>
              </ul>
              <p v-else class="empty inline">None.</p>

              <span class="save-lbl added">Added · {{ saveResult.triples_added.length }} relations</span>
              <ul v-if="saveResult.triples_added.length" class="save-list">
                <li v-for="x in saveResult.triples_added" :key="x" class="save-item added">{{ x }}</li>
              </ul>
              <p v-else class="empty inline">None.</p>
            </div>

            <div class="save-col">
              <span class="save-lbl skipped">Skipped · {{ saveResult.instances_skipped.length + saveResult.triples_skipped.length }}</span>
              <p class="caption">Already present in the ontology.</p>
              <ul v-if="saveResult.instances_skipped.length || saveResult.triples_skipped.length" class="save-list">
                <li v-for="x in saveResult.instances_skipped" :key="`is-${x}`" class="save-item skipped">{{ x }}</li>
                <li v-for="x in saveResult.triples_skipped" :key="`ts-${x}`" class="save-item skipped">{{ x }}</li>
              </ul>

              <template v-if="saveResult.errors.length">
                <span class="save-lbl errored">Errors · {{ saveResult.errors.length }}</span>
                <ul class="save-list">
                  <li v-for="x in saveResult.errors" :key="x" class="save-item errored">{{ x }}</li>
                </ul>
              </template>
            </div>
          </div>

          <!-- Validation agent section (only shown when validation actually ran) -->
          <section v-if="['validating','validated'].includes(stage) || validationError" class="validate-section">
            <header class="validate-head">
              <div>
                <h4>Validation agent</h4>
                <p>
                  A second LLM agent is re-reading the ontology and proposing corrections you can
                  approve or reject.
                </p>
              </div>
            </header>

            <p v-if="validationError" class="error">
              <span class="error-icon">!</span>{{ validationError }}
            </p>

            <!-- Live status + log during validation, persists after done -->
            <div v-if="['validating','validated'].includes(stage)" class="validate-status">
              <div class="validate-status-row">
                <span :class="['badge', stage === 'validated' ? 'badge-done' : 'badge-running']">
                  <span class="badge-dot" />
                  {{ stage === 'validated' ? 'done' : 'running' }}
                </span>
                <span v-if="validationId" class="job-id">job · {{ validationId }}</span>
              </div>

              <div v-if="validationLog.length" class="logs">
                <header class="logs-head">
                  <span>./validation · log</span>
                  <span>{{ validationLog.length }} lines</span>
                </header>
                <pre>{{ validationLog.join('\n') }}</pre>
              </div>
            </div>

            <template v-if="stage === 'validated'">
              <div v-if="!fixes.length" class="validation-clean">
                <span class="ok-mark">✓</span>
                Validation finished — the agent did not propose any corrections.
              </div>

              <div v-else class="fixes">
                <header class="fixes-head">
                  <h5>{{ fixes.length }} proposed fix{{ fixes.length === 1 ? '' : 'es' }}</h5>
                  <span class="caption">Approve what looks right; reject the rest.</span>
                </header>
                <article v-for="(fix, i) in fixes" :key="fix.fix_id ?? fix.id" class="fix">
                  <span class="fix-num">{{ String(i + 1).padStart(2, '0') }}</span>
                  <div class="fix-body">
                    <span v-if="fix.kind || fix.type" class="fix-tag">{{ fix.kind || fix.type }}</span>
                    <p>{{ fixSummary(fix) }}</p>
                  </div>
                  <div class="fix-actions">
                    <span
                      v-if="fixDecisions[fix.fix_id ?? fix.id]"
                      :class="['decided', fixDecisions[fix.fix_id ?? fix.id]]"
                    >
                      {{ fixDecisions[fix.fix_id ?? fix.id] }}
                    </span>
                    <template v-else>
                      <button class="btn small approve" type="button" @click="decideFix(fix, 'approve')">Approve</button>
                      <button class="btn small reject" type="button" @click="decideFix(fix, 'reject')">Reject</button>
                    </template>
                  </div>
                </article>
              </div>
            </template>
          </section>

          <footer class="approve-bar">
            <button type="button" class="btn ghost" @click="reset">Extract another</button>
          </footer>
        </template>
      </div>
    </div>
  </section>
</template>

<style scoped>
.page {
  max-width: 1320px;
  margin: 0 auto;
  padding: var(--s-6) var(--s-6) var(--s-9);
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
  animation: fade-up 380ms var(--ease) both;
}

.page-head {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.kicker {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--brand);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-weight: 500;
}

.page-head h2 {
  font-size: var(--t-2xl);
  font-weight: 600;
  letter-spacing: -0.025em;
  color: var(--text);
}

.page-head p {
  font-size: var(--t-md);
  color: var(--text-muted);
  max-width: 64ch;
}

/* progress rail */
.rail {
  display: flex;
  gap: var(--s-3);
  list-style: none;
  padding: 0;
}

.rail li {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  padding: 6px var(--s-3);
  background: var(--bg-tint);
  border: 1px solid var(--border);
  border-radius: var(--r-pill);
  font-size: var(--t-sm);
  color: var(--text-muted);
  transition: all var(--speed) var(--ease);
}

.rail li.active {
  background: var(--brand-soft);
  color: var(--brand);
  border-color: color-mix(in srgb, var(--brand) 25%, transparent);
}

.rail li.done {
  background: var(--success-soft);
  color: var(--success);
  border-color: #c5ecd0;
}

.rail-num {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  background: currentColor;
  color: white !important;
}

.rail li.active .rail-num,
.rail li.done .rail-num {
  background: currentColor;
}

.rail-lbl {
  font-weight: 500;
}

.grid {
  display: grid;
  grid-template-columns: minmax(420px, 1fr) minmax(520px, 1.6fr);
  gap: var(--s-5);
  align-items: start;
}

.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  padding: var(--s-5);
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  box-shadow: var(--shadow-xs);
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: var(--s-3);
  padding-bottom: var(--s-3);
  border-bottom: 1px solid var(--border);
}

.card-head h3 {
  font-size: var(--t-md);
  font-weight: 600;
  letter-spacing: -0.01em;
}

.link {
  font-size: 12px;
  color: var(--brand);
  font-weight: 500;
  padding: 2px var(--s-2);
  border-radius: var(--r-sm);
  transition: background var(--speed) var(--ease);
}

.link:hover {
  background: var(--brand-soft);
}

.field {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.lbl {
  font-size: var(--t-sm);
  font-weight: 500;
  color: var(--text);
}

.textarea-wrap {
  position: relative;
}

textarea {
  width: 100%;
  font-family: var(--font);
  font-size: var(--t-sm);
  line-height: 1.6;
  padding: var(--s-3);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  background: var(--surface);
  color: var(--text);
  resize: vertical;
  outline: none;
  transition: border-color var(--speed) var(--ease), box-shadow var(--speed) var(--ease);
}

textarea:read-only {
  background: var(--bg-tint);
  color: var(--text-soft);
  cursor: default;
}

textarea:focus:not(:read-only) {
  border-color: var(--border-focus);
  box-shadow: var(--shadow-focus);
}

textarea::placeholder {
  color: var(--text-faint);
}

.counter {
  position: absolute;
  right: var(--s-3);
  bottom: var(--s-2);
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
  background: var(--surface);
  padding: 2px var(--s-2);
  border-radius: var(--r-sm);
  border: 1px solid var(--border);
}

.actions {
  display: flex;
  gap: var(--s-3);
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  padding: var(--s-3) var(--s-4);
  border-radius: var(--r-sm);
  font-size: var(--t-sm);
  font-weight: 500;
  transition:
    background var(--speed) var(--ease),
    color var(--speed) var(--ease),
    border-color var(--speed) var(--ease),
    box-shadow var(--speed) var(--ease);
}

.btn .arrow {
  transition: transform var(--speed) var(--ease);
}
.btn:hover:not(:disabled) .arrow {
  transform: translateX(3px);
}

.btn.primary {
  background: var(--brand);
  color: white;
}

.btn.primary:hover:not(:disabled) {
  background: var(--brand-hover);
  box-shadow: var(--shadow-sm);
}

.btn.ghost {
  background: var(--surface);
  border: 1px solid var(--border);
  color: var(--text-soft);
}

.btn.ghost:hover:not(:disabled) {
  border-color: var(--border-strong);
  color: var(--text);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error {
  display: flex;
  gap: var(--s-2);
  align-items: center;
  font-size: var(--t-sm);
  color: var(--danger);
  background: var(--danger-soft);
  border: 1px solid #f5c6cb;
  padding: var(--s-3);
  border-radius: var(--r-sm);
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

.result {
  min-height: 420px;
}

.meta-pill {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-muted);
}

.note {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  padding: var(--s-2) var(--s-3);
  background: var(--brand-tint);
  border: 1px solid color-mix(in srgb, var(--brand) 18%, transparent);
  border-radius: var(--r-sm);
  font-size: var(--t-sm);
  color: var(--brand-deep);
}

.note-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--brand);
  flex-shrink: 0;
}

.empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--s-3);
  padding: var(--s-7);
  color: var(--text-muted);
  font-size: var(--t-sm);
  text-align: center;
}

.empty.inline {
  padding: var(--s-2) 0;
  justify-content: flex-start;
}

.empty.loading {
  flex-direction: column;
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

.spinner.big {
  width: 24px;
  height: 24px;
  border-width: 2px;
  color: var(--brand);
}

.block {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.block-head {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  padding: var(--s-2) var(--s-3);
  border-radius: var(--r-sm);
  font-size: var(--t-sm);
}

.block-head.accept {
  background: var(--success-soft);
  color: var(--success);
  border: 1px solid #c5ecd0;
}

.block-head.reject {
  background: var(--warning-soft);
  color: var(--warning);
  border: 1px solid #fad8a3;
}

.block-title {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  font-weight: 600;
}

.accept-mark,
.reject-mark {
  font-size: 14px;
  font-weight: 700;
}

.block-count {
  font-family: var(--font-mono);
  font-size: 12px;
  opacity: 0.75;
}

.block-actions {
  margin-left: auto;
  display: flex;
  gap: var(--s-1);
}

.micro {
  font-size: 11px;
  font-family: var(--font-mono);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 2px var(--s-2);
  border-radius: var(--r-sm);
  color: currentColor;
  opacity: 0.7;
  transition: opacity var(--speed) var(--ease), background var(--speed) var(--ease);
}

.micro:hover {
  opacity: 1;
  background: rgba(255, 255, 255, 0.5);
}

.block-note {
  font-size: 12px;
  color: var(--text-muted);
  font-style: italic;
}

.entity-group {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.group-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-weight: 600;
}

.rows {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
}

.row {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  padding: var(--s-2) var(--s-3);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  cursor: pointer;
  transition: border-color var(--speed) var(--ease), background var(--speed) var(--ease), opacity var(--speed) var(--ease);
}

.row:hover {
  border-color: var(--border-strong);
}

.row.unchecked {
  opacity: 0.5;
  background: var(--bg-tint);
}

.row input[type='checkbox'] {
  accent-color: var(--brand);
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  cursor: pointer;
}

.row-name {
  font-size: var(--t-sm);
  font-weight: 500;
  color: var(--text);
}

.row-name.mono {
  font-family: var(--font-mono);
  font-size: 13px;
}

.row-arrow {
  color: var(--text-faint);
  font-size: 12px;
}

.row-type {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--brand);
  background: var(--brand-soft);
  padding: 2px var(--s-2);
  border-radius: var(--r-sm);
  margin-left: auto;
}

.rejected-row {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: var(--s-3);
  align-items: center;
}

.rejected-row.picked {
  border-color: var(--brand);
  background: var(--brand-tint);
}

.rejected-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.row-reason {
  font-size: 11px;
  color: var(--text-muted);
  font-style: italic;
}

.type-select {
  appearance: none;
  -webkit-appearance: none;
  padding: 4px var(--s-5) 4px var(--s-2);
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  background-color: var(--surface);
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 12 12' fill='none' stroke='%236b7785' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M3 4.5l3 3 3-3'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 6px center;
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  color: var(--text);
  cursor: pointer;
}

.type-select:focus {
  outline: none;
  border-color: var(--brand);
}

.type-select:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.triple-row {
  display: grid;
  grid-template-columns: auto 1fr auto 1fr;
  gap: var(--s-2);
  align-items: center;
}

.triple-s,
.triple-o {
  font-size: var(--t-sm);
  color: var(--text);
  font-weight: 500;
}

.triple-p {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--accent);
  background: var(--accent-soft);
  padding: 2px var(--s-2);
  border-radius: var(--r-sm);
  text-align: center;
}

.raw summary {
  cursor: pointer;
  font-size: var(--t-sm);
  color: var(--text-muted);
  font-weight: 500;
  user-select: none;
  padding: var(--s-2) 0;
}

.raw summary:hover {
  color: var(--text);
}

.raw pre {
  margin-top: var(--s-2);
  padding: var(--s-3);
  background: #0b1320;
  color: #d6dde7;
  border-radius: var(--r-sm);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  max-height: 320px;
  overflow: auto;
}

.approve-bar {
  display: flex;
  justify-content: space-between;
  gap: var(--s-3);
  padding-top: var(--s-3);
  margin-top: var(--s-2);
  border-top: 1px solid var(--border);
}

.saved-banner {
  display: flex;
  gap: var(--s-3);
  align-items: center;
  padding: var(--s-4);
  background: linear-gradient(135deg, var(--success-soft) 0%, #f0fbf3 100%);
  border: 1px solid #c5ecd0;
  border-radius: var(--r-md);
}

.saved-icon {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--success);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.saved-banner h4 {
  font-size: var(--t-md);
  font-weight: 600;
  color: var(--success);
}

.saved-banner p {
  font-size: var(--t-sm);
  color: var(--text-soft);
  margin-top: 2px;
}

.save-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--s-4);
}

.save-col {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.save-lbl {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 600;
  margin-top: var(--s-2);
}

.save-lbl.added {
  color: var(--success);
}
.save-lbl.skipped {
  color: var(--text-muted);
}
.save-lbl.errored {
  color: var(--danger);
}

.save-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 200px;
  overflow-y: auto;
}

.save-item {
  font-family: var(--font-mono);
  font-size: 12px;
  padding: 4px var(--s-2);
  border-radius: var(--r-sm);
  border-left: 2px solid;
}

.save-item.added {
  color: var(--success);
  background: var(--success-soft);
  border-left-color: var(--success);
}

.save-item.skipped {
  color: var(--text-muted);
  background: var(--bg-tint);
  border-left-color: var(--text-faint);
}

.save-item.errored {
  color: var(--danger);
  background: var(--danger-soft);
  border-left-color: var(--danger);
}

.caption {
  font-size: 12px;
  color: var(--text-muted);
}

/* Validation toggle (in review screen, before save) */
.validate-toggle {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--s-3);
  padding: var(--s-3) var(--s-4);
  margin-top: var(--s-3);
  background: var(--brand-tint);
  border: 1px solid color-mix(in srgb, var(--brand) 18%, transparent);
  border-radius: var(--r-sm);
  cursor: pointer;
  align-items: start;
}

.validate-toggle input[type='checkbox'] {
  margin-top: 2px;
  accent-color: var(--brand);
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.validate-toggle-title {
  font-size: var(--t-sm);
  font-weight: 600;
  color: var(--text);
  display: flex;
  align-items: center;
  gap: var(--s-2);
}

.validate-toggle-body {
  font-size: 12px;
  color: var(--text-soft);
  line-height: 1.55;
  margin-top: 4px;
  max-width: 60ch;
}

/* Validation agent panel */
.validate-section {
  margin-top: var(--s-5);
  padding-top: var(--s-5);
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}

.validate-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--s-4);
}

.validate-head h4 {
  font-size: var(--t-md);
  font-weight: 600;
  color: var(--text);
  letter-spacing: -0.01em;
}

.validate-head p {
  font-size: var(--t-sm);
  color: var(--text-muted);
  margin-top: 4px;
  max-width: 56ch;
  line-height: 1.55;
}

.validation-clean {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  padding: var(--s-3) var(--s-4);
  background: var(--success-soft);
  border: 1px solid #c5ecd0;
  border-radius: var(--r-sm);
  font-size: var(--t-sm);
  color: var(--success);
  font-weight: 500;
}

.validate-status {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}

.validate-status-row {
  display: flex;
  align-items: center;
  gap: var(--s-3);
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  padding: 6px var(--s-3);
  border-radius: var(--r-sm);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.badge-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
}

.badge-running {
  background: var(--brand-soft);
  color: var(--brand);
  border: 1px solid color-mix(in srgb, var(--brand) 25%, transparent);
}

.badge-running .badge-dot {
  animation: pulse 1.4s var(--ease) infinite;
}

.badge-done {
  background: var(--success-soft);
  color: var(--success);
  border: 1px solid #c5ecd0;
}

.job-id {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-muted);
}

.logs {
  background: #0b1320;
  color: #d6dde7;
  border-radius: var(--r-md);
  overflow: hidden;
  border: 1px solid #1f2a3c;
}

.logs-head {
  display: flex;
  justify-content: space-between;
  padding: var(--s-2) var(--s-3);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #8b97a8;
  border-bottom: 1px solid #1f2a3c;
}

.logs pre {
  padding: var(--s-3);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 260px;
  overflow: auto;
}

.ok-mark {
  font-size: 16px;
  font-weight: 700;
}

.fixes {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}

.fixes-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: var(--s-3);
}

.fixes-head h5 {
  font-size: var(--t-sm);
  font-weight: 600;
  color: var(--text);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.fix {
  display: grid;
  grid-template-columns: 32px 1fr auto;
  gap: var(--s-3);
  padding: var(--s-3) var(--s-4);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  align-items: flex-start;
}

.fix-num {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
  color: var(--brand);
  padding-top: 2px;
}

.fix-body {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.fix-tag {
  align-self: flex-start;
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--brand);
  background: var(--brand-soft);
  padding: 2px 6px;
  border-radius: var(--r-sm);
}

.fix-body p {
  font-size: 13px;
  color: var(--text);
  line-height: 1.55;
}

.fix-actions {
  display: flex;
  gap: var(--s-2);
}

.decided {
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 4px var(--s-2);
  border-radius: var(--r-sm);
}

.decided.approve {
  background: var(--success-soft);
  color: var(--success);
}

.decided.reject {
  background: var(--danger-soft);
  color: var(--danger);
}

.decided.pending {
  background: var(--bg-tint);
  color: var(--text-muted);
}

.decided.error {
  background: var(--danger-soft);
  color: var(--danger);
}

@media (max-width: 1100px) {
  .grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 700px) {
  .triple-row {
    grid-template-columns: auto 1fr;
  }
  .triple-row .triple-p,
  .triple-row .triple-o {
    grid-column: 2;
  }
  .save-grid {
    grid-template-columns: 1fr;
  }
}
</style>
