<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from '../api.js'
import ModelSelector from './ModelSelector.vue'

const POLL_MS = 2000

// --- form state ---
const days = ref(30)
const model = ref(null)

const runValidation = ref(true)
const validationPasses = ref(2)

const runDLLearner = ref(false)
const dllExperiment = ref('')
const experiments = ref([])

const runHermit = ref(false)

const showAdvanced = ref(false)

// --- pipeline state ---
const pipelineActive = ref(false)
const pipelineDone = ref(false)
const pipelineError = ref('')
const currentStep = ref(null)
const completedSteps = ref([])
const overallLog = ref([])

const litState = ref(null)
const litResult = ref(null)
const litId = ref(null)

const awaitingApproval = ref(false)
const selectedPmids = ref(new Set())
const approveResult = ref(null)

const miningState = ref(null)
const miningResult = ref(null)
const miningId = ref(null)

const ontologyBefore = ref(null)
const miningChanges = ref(null)
const instancesToRemove = ref(new Set())
const awaitingMiningReview = ref(false)

const validationState = ref(null)
const validationId = ref(null)
const fixes = ref([])
const decided = ref({})
const awaitingValidationReview = ref(false)
let _validationReviewResolve = null

const dlState = ref(null)
const dlResult = ref(null)
const dlId = ref(null)

const hermitState = ref(null)
const hermitResult = ref(null)
const hermitId = ref(null)

// Rejected literature drawer
const rejectedOpen = ref(false)
const rejectedItems = ref([])
const rejectedLoading = ref(false)
const rejectedError = ref('')
const restoringPmids = ref(new Set())
const selectedRejectedPmids = ref(new Set())
const bulkRestoring = ref(false)

// Approved literature drawer
const approvedOpen = ref(false)
const approvedItems = ref([])
const approvedLoading = ref(false)
const approvedError = ref('')

let activeTimer = null
let cancelled = false

const plannedSteps = computed(() => {
  const steps = [
    { key: 'literature', label: 'Find papers' },
    { key: 'approval', label: 'Pick papers' },
    { key: 'process', label: 'Extract entities' },
    { key: 'review-mining', label: 'Review additions' },
  ]
  if (runValidation.value) steps.push({ key: 'validation', label: 'Validate' })
  if (runHermit.value) steps.push({ key: 'hermit', label: 'HermiT reasoner' })
  if (runDLLearner.value && dllExperiment.value) steps.push({ key: 'dllearner', label: 'DL-Learner' })
  return steps
})

const stepIndex = computed(() => {
  if (!currentStep.value) return -1
  return plannedSteps.value.findIndex((s) => s.key === currentStep.value)
})

function currentStepProgress() {
  let s = null
  if (currentStep.value === 'literature') s = litState.value
  else if (currentStep.value === 'process') s = miningState.value
  else if (currentStep.value === 'validation') s = validationState.value
  else if (currentStep.value === 'hermit') s = hermitState.value
  else if (currentStep.value === 'dllearner') s = dlState.value
  else if (currentStep.value === 'approval' || currentStep.value === 'review-mining') return 0
  if (!s) return 0
  const p = typeof s.progress === 'number' ? s.progress : 0
  return Math.max(0, Math.min(1, p))
}

const overallPct = computed(() => {
  if (!pipelineActive.value && !pipelineDone.value && !awaitingApproval.value && !awaitingMiningReview.value) return 0
  if (pipelineDone.value) return 100
  const total = plannedSteps.value.length
  if (total === 0 || stepIndex.value < 0) return 0
  return Math.min(99, Math.round(((stepIndex.value + currentStepProgress()) / total) * 100))
})

function clearTimer() {
  if (activeTimer) {
    clearTimeout(activeTimer)
    activeTimer = null
  }
}

function pushLog(line) {
  if (!line) return
  overallLog.value = [...overallLog.value, line]
}

function pushLogs(lines) {
  if (!Array.isArray(lines) || !lines.length) return
  const last = overallLog.value.slice(-lines.length).join('\n')
  if (last === lines.join('\n')) return
  overallLog.value = [...overallLog.value, ...lines]
}

async function pollJob(jobId, stateRef) {
  return new Promise((resolve, reject) => {
    const tick = async () => {
      if (cancelled) return reject(new Error('Pipeline cancelled'))
      try {
        const state = await api.getRun(jobId)
        stateRef.value = state
        if (Array.isArray(state.log_tail)) pushLogs(state.log_tail)
        if (state.status === 'done' || state.status === 'completed') return resolve(state)
        if (state.status === 'error' || state.status === 'failed') {
          return reject(new Error(state.error || 'Job reported error'))
        }
        activeTimer = setTimeout(tick, POLL_MS)
      } catch (err) {
        reject(err)
      }
    }
    tick()
  })
}

function resetPipelineState() {
  litState.value = null
  litResult.value = null
  litId.value = null
  awaitingApproval.value = false
  selectedPmids.value = new Set()
  approveResult.value = null
  miningState.value = null
  miningResult.value = null
  miningId.value = null
  ontologyBefore.value = null
  miningChanges.value = null
  instancesToRemove.value = new Set()
  awaitingMiningReview.value = false
  validationState.value = null
  validationId.value = null
  fixes.value = []
  decided.value = {}
  awaitingValidationReview.value = false
  _validationReviewResolve = null
  dlState.value = null
  dlResult.value = null
  dlId.value = null
  hermitState.value = null
  hermitResult.value = null
  hermitId.value = null
}

function computeOntologyDiff(before, after) {
  const beforeClasses = before?.classes || {}
  const afterClasses = after?.classes || {}
  const newClasses = []
  const newInstances = []

  for (const [className, def] of Object.entries(afterClasses)) {
    if (!beforeClasses[className]) {
      newClasses.push(className)
      for (const inst of def.instances || []) newInstances.push({ name: inst, type: className })
    } else {
      const beforeInsts = new Set(beforeClasses[className].instances || [])
      for (const inst of def.instances || []) {
        if (!beforeInsts.has(inst)) newInstances.push({ name: inst, type: className })
      }
    }
  }

  const beforeProps = before?.properties || {}
  const afterProps = after?.properties || {}
  const newTriples = []
  for (const [predName, def] of Object.entries(afterProps)) {
    const beforeExamples = new Set((beforeProps[predName]?.examples || []).map((t) => t.join('|')))
    for (const t of def.examples || []) {
      if (!beforeExamples.has(t.join('|'))) {
        newTriples.push({ subject: t[0], predicate: t[1], object: t[2] })
      }
    }
  }
  return { newClasses, newInstances, newTriples }
}

async function runPostMining() {
  if (runValidation.value) {
    currentStep.value = 'validation'
    pushLog(`▶ Validation agent running (${validationPasses.value} pass${validationPasses.value === 1 ? '' : 'es'})…`)
    const valStart = await api.startValidation({
      model: model.value.id,
      provider: model.value.provider,
      max_passes: Number(validationPasses.value) || 1,
    })
    validationId.value = valStart.job_id
    await pollJob(valStart.job_id, validationState)
    try {
      const data = await api.getFixes(valStart.job_id)
      fixes.value = Array.isArray(data) ? data : data.fixes || []
      pushLog(`✓ Validation: ${fixes.value.length} proposed fix${fixes.value.length === 1 ? '' : 'es'}.`)
    } catch (err) {
      pushLog(`! Fixes fetch failed: ${err.message}`)
    }
    completedSteps.value = [...completedSteps.value, 'validation']

    if (fixes.value.length > 0 && (runHermit.value || (runDLLearner.value && dllExperiment.value))) {
      pushLog(`Review fixes below, then click "Continue" to proceed.`)
      awaitingValidationReview.value = true
      await new Promise((resolve) => { _validationReviewResolve = resolve })
      awaitingValidationReview.value = false
    }
  }

  if (runHermit.value) {
    currentStep.value = 'hermit'
    pushLog(`▶ HermiT reasoner classifying the ontology…`)
    try {
      const hStart = await api.runHermit()
      hermitId.value = hStart.job_id
      await pollJob(hStart.job_id, hermitState)
      hermitResult.value = await api.getHermitResult(hStart.job_id)
      const consistent = hermitResult.value?.consistent
      const inferred = hermitResult.value?.inferred_axioms?.length ?? 0
      const unsat = hermitResult.value?.unsatisfiable_classes?.length ?? 0
      pushLog(
        `✓ HermiT: ${consistent === false ? 'INCONSISTENT' : 'consistent'}, ` +
          `${inferred} inferred axiom${inferred === 1 ? '' : 's'}` +
          (unsat ? `, ${unsat} unsatisfiable class${unsat === 1 ? '' : 'es'}` : ''),
      )
    } catch (err) {
      pushLog(`! HermiT failed: ${err.message}`)
    }
    completedSteps.value = [...completedSteps.value, 'hermit']
  }

  if (runDLLearner.value && dllExperiment.value) {
    currentStep.value = 'dllearner'
    const exp = experiments.value.find((e) => e.name === dllExperiment.value)
    pushLog(`▶ DL-Learner · ${exp?.title || dllExperiment.value}…`)
    const dlStart = await api.runDLLearner({ experiment: dllExperiment.value })
    dlId.value = dlStart.job_id
    await pollJob(dlStart.job_id, dlState)
    try {
      dlResult.value = await api.getDLResult(dlStart.job_id)
      const top = dlResult.value?.solutions?.[0]
      pushLog(`✓ DL-Learner top: ${top?.expression || top?.description || 'no result'}`)
    } catch (err) {
      pushLog(`! DL-Learner result fetch failed: ${err.message}`)
    }
    completedSteps.value = [...completedSteps.value, 'dllearner']
  }

  pipelineActive.value = false
  pipelineDone.value = true
  currentStep.value = null
  pushLog(`✓ Pipeline complete.`)
}

async function pauseForMiningReview() {
  try {
    const after = await api.getOntology()
    miningChanges.value = computeOntologyDiff(ontologyBefore.value, after)
  } catch (err) {
    pushLog(`! Failed to compute diff: ${err.message}`)
    miningChanges.value = { newClasses: [], newInstances: [], newTriples: [] }
  }
  instancesToRemove.value = new Set()
  currentStep.value = 'review-mining'
  awaitingMiningReview.value = true
  pipelineActive.value = false
  const c = miningChanges.value
  pushLog(
    `✓ Mining added ${c.newClasses.length} class${c.newClasses.length === 1 ? '' : 'es'}, ` +
      `${c.newInstances.length} instance${c.newInstances.length === 1 ? '' : 's'}, ` +
      `${c.newTriples.length} relation${c.newTriples.length === 1 ? '' : 's'}. Awaiting your review…`,
  )
}

async function startPipeline() {
  if (!model.value) return
  cancelled = false
  pipelineActive.value = true
  pipelineDone.value = false
  pipelineError.value = ''
  currentStep.value = null
  completedSteps.value = []
  overallLog.value = []
  resetPipelineState()

  try {
    currentStep.value = 'literature'
    pushLog(`▶ Searching PubMed for AMD papers (last ${days.value} days)…`)
    const start = await api.fetchLiterature({
      days: Number(days.value),
      model: model.value.id,
      provider: model.value.provider,
    })
    litId.value = start.job_id
    await pollJob(start.job_id, litState)
    try {
      litResult.value = await api.getLiteratureResult(start.job_id)
      const props = litResult.value?.proposals?.length ?? 0
      pushLog(`✓ Found ${props} paper${props === 1 ? '' : 's'}. Pick the ones to mine…`)
    } catch (err) {
      pushLog(`! Literature result fetch failed: ${err.message}`)
      throw err
    }
    completedSteps.value = [...completedSteps.value, 'literature']

    const preSel = new Set()
    for (const p of litResult.value?.proposals || []) {
      const rel = String(p.relevance || '').toUpperCase()
      if ((rel === 'RELEVANT' || rel === 'HIGH') && p.pmid) preSel.add(String(p.pmid))
    }
    selectedPmids.value = preSel

    currentStep.value = 'approval'
    awaitingApproval.value = true
  } catch (err) {
    pipelineActive.value = false
    pipelineError.value = err.response?.data?.detail || err.message || 'Pipeline failed'
    pushLog(`✗ ${pipelineError.value}`)
  }
}

function cancelPipeline() {
  cancelled = true
  clearTimer()
  pipelineActive.value = false
  awaitingApproval.value = false
  awaitingMiningReview.value = false
  pipelineError.value = 'Cancelled by user'
}

function togglePmid(pmid) {
  const next = new Set(selectedPmids.value)
  const key = String(pmid)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  selectedPmids.value = next
}

function selectAllProposals() {
  const next = new Set()
  for (const p of litResult.value?.proposals || []) if (p.pmid) next.add(String(p.pmid))
  selectedPmids.value = next
}

function clearProposalSelection() {
  selectedPmids.value = new Set()
}

async function continueAfterApproval() {
  if (!awaitingApproval.value || selectedPmids.value.size === 0) return
  awaitingApproval.value = false
  pipelineActive.value = true
  cancelled = false

  try {
    const ids = Array.from(selectedPmids.value)
    pushLog(`▶ Saving ${ids.length} paper${ids.length === 1 ? '' : 's'}…`)
    const approve = await api.approveLiterature({
      proposals: litResult.value?.proposals || [],
      pmids_to_keep: ids,
    })
    approveResult.value = approve
    const saved = approve.saved || []
    const skipped = approve.skipped_missing_text || []
    pushLog(`✓ Saved ${saved.length}${skipped.length ? `, ${skipped.length} skipped (missing text)` : ''}.`)
    completedSteps.value = [...completedSteps.value, 'approval']

    if (!saved.length) throw new Error('No papers were saved — none can be processed.')

    try {
      ontologyBefore.value = await api.getOntology()
    } catch (err) {
      pushLog(`! Could not snapshot ontology before mining: ${err.message}`)
      ontologyBefore.value = { classes: {}, properties: {} }
    }
    currentStep.value = 'process'
    pushLog(`▶ Extracting entities and relations from ${saved.length} paper${saved.length === 1 ? '' : 's'}…`)
    const proc = await api.processLiterature({
      pmids: saved,
      model: model.value.id,
      provider: model.value.provider,
      use_current_ontology: true,
    })
    miningId.value = proc.job_id
    await pollJob(proc.job_id, miningState)
    try {
      miningResult.value = await api.getRunResult(proc.job_id)
    } catch (err) {
      pushLog(`! Mining result fetch failed: ${err.message}`)
    }
    pushLog(`✓ Extraction complete.`)
    completedSteps.value = [...completedSteps.value, 'process']

    await pauseForMiningReview()
  } catch (err) {
    pipelineActive.value = false
    pipelineError.value = err.response?.data?.detail || err.message || 'Pipeline failed'
    pushLog(`✗ ${pipelineError.value}`)
  }
}

function toggleInstanceRemoval(name) {
  const next = new Set(instancesToRemove.value)
  if (next.has(name)) next.delete(name)
  else next.add(name)
  instancesToRemove.value = next
}

function removeAllInstances() {
  const next = new Set()
  for (const i of miningChanges.value?.newInstances || []) next.add(i.name)
  instancesToRemove.value = next
}

function keepAllInstances() {
  instancesToRemove.value = new Set()
}

async function confirmMiningChanges() {
  if (!awaitingMiningReview.value) return
  awaitingMiningReview.value = false
  pipelineActive.value = true
  cancelled = false

  try {
    const toRemove = Array.from(instancesToRemove.value)
    if (toRemove.length) {
      pushLog(`▶ Removing ${toRemove.length} unwanted item${toRemove.length === 1 ? '' : 's'}…`)
      let removed = 0
      let failed = 0
      for (const name of toRemove) {
        try {
          await api.deleteInstance(name)
          pushLog(`  − ${name}`)
          removed += 1
        } catch (err) {
          pushLog(`  ! Failed to remove ${name}: ${err.message}`)
          failed += 1
        }
      }
      pushLog(`✓ Removed ${removed}${failed ? `, ${failed} failed` : ''}.`)
    } else {
      pushLog(`✓ All additions kept.`)
    }
    completedSteps.value = [...completedSteps.value, 'review-mining']

    await runPostMining()
  } catch (err) {
    pipelineActive.value = false
    pipelineError.value = err.response?.data?.detail || err.message || 'Pipeline failed'
    pushLog(`✗ ${pipelineError.value}`)
  }
}

function continueAfterValidation() {
  if (_validationReviewResolve) {
    _validationReviewResolve()
    _validationReviewResolve = null
  }
}

async function decide(fix, action) {
  const fixId = fix.fix_id ?? fix.id
  decided.value = { ...decided.value, [fixId]: 'pending' }
  try {
    await api.decideFix(validationId.value, fixId, action)
    decided.value = { ...decided.value, [fixId]: action }
  } catch (err) {
    decided.value = { ...decided.value, [fixId]: 'error' }
    pipelineError.value = err.response?.data?.detail || err.message || 'Decision failed'
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

const stepStatus = (key) => {
  if (completedSteps.value.includes(key)) return 'done'
  if (currentStep.value === key) return 'active'
  return 'pending'
}

const groupedNewInstances = computed(() => {
  if (!miningChanges.value?.newInstances?.length) return []
  const map = new Map()
  for (const i of miningChanges.value.newInstances) {
    if (!map.has(i.type)) map.set(i.type, [])
    map.get(i.type).push(i)
  }
  return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b))
})

const keptCount = computed(() => {
  const total = miningChanges.value?.newInstances?.length || 0
  return total - instancesToRemove.value.size
})

const HOW_IT_WORKS = [
  { num: '1', title: 'Find papers', body: 'PubMed is searched for AMD papers in your chosen date range.', icon: 'search', actor: 'auto' },
  { num: '2', title: 'You pick', body: 'Tick the papers worth mining. Suggestions are pre-sorted by relevance.', icon: 'check', actor: 'human' },
  { num: '3', title: 'AI extracts', body: 'An LLM agent reads each paper and proposes new entities and relations.', icon: 'sparkle', actor: 'auto' },
  { num: '4', title: 'You confirm', body: "See exactly what was added. Untick anything that doesn't belong.", icon: 'eye', actor: 'human' },
  { num: '5', title: 'Validation', body: 'A second agent re-reads the ontology and proposes corrections for your review.', icon: 'shield', actor: 'auto' },
]


watch(runDLLearner, async (v) => {
  if (v && experiments.value.length === 0) {
    try {
      experiments.value = await api.listDLExperiments()
      if (experiments.value.length && !dllExperiment.value) {
        dllExperiment.value = experiments.value[0].name
      }
    } catch (err) {
      pipelineError.value = `Failed to load DL-Learner experiments: ${err.message}`
    }
  }
})

async function loadRejected() {
  rejectedLoading.value = true
  rejectedError.value = ''
  try {
    const data = await api.getRejectedLiterature()
    rejectedItems.value = Array.isArray(data) ? data : data.rejected || []
    selectedRejectedPmids.value = new Set()
  } catch (err) {
    rejectedError.value = err.response?.data?.detail || err.message || 'Failed to load rejected'
  } finally {
    rejectedLoading.value = false
  }
}

async function toggleRejected() {
  rejectedOpen.value = !rejectedOpen.value
  if (rejectedOpen.value && rejectedItems.value.length === 0) {
    await loadRejected()
  }
}

function toggleRejectedPmid(pmid) {
  if (!pmid) return
  const next = new Set(selectedRejectedPmids.value)
  const key = String(pmid)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  selectedRejectedPmids.value = next
}

function selectAllRejected() {
  const next = new Set()
  for (const r of rejectedItems.value) if (r.pmid) next.add(String(r.pmid))
  selectedRejectedPmids.value = next
}

function clearRejectedSelection() {
  selectedRejectedPmids.value = new Set()
}

async function restoreSelectedRejected() {
  if (selectedRejectedPmids.value.size === 0) return
  bulkRestoring.value = true
  rejectedError.value = ''
  const ids = Array.from(selectedRejectedPmids.value)
  try {
    await api.restoreRejectedLiterature(ids)
    rejectedItems.value = rejectedItems.value.filter(
      (r) => !ids.includes(String(r.pmid)),
    )
    selectedRejectedPmids.value = new Set()
  } catch (err) {
    rejectedError.value = err.response?.data?.detail || err.message || 'Restore failed'
  } finally {
    bulkRestoring.value = false
  }
}

async function restoreRejected(pmid) {
  if (!pmid) return
  const next = new Set(restoringPmids.value)
  next.add(pmid)
  restoringPmids.value = next
  try {
    await api.restoreRejectedLiterature([pmid])
    rejectedItems.value = rejectedItems.value.filter((r) => String(r.pmid) !== String(pmid))
  } catch (err) {
    rejectedError.value = err.response?.data?.detail || err.message || 'Restore failed'
  } finally {
    const after = new Set(restoringPmids.value)
    after.delete(pmid)
    restoringPmids.value = after
  }
}

async function loadApproved() {
  approvedLoading.value = true
  approvedError.value = ''
  try {
    const data = await api.getApprovedLiterature()
    approvedItems.value = Array.isArray(data) ? data : data.approved || []
  } catch (err) {
    approvedError.value = err.response?.data?.detail || err.message || 'Failed to load approved'
  } finally {
    approvedLoading.value = false
  }
}

async function toggleApproved() {
  approvedOpen.value = !approvedOpen.value
  if (approvedOpen.value && approvedItems.value.length === 0) {
    await loadApproved()
  }
}

onMounted(async () => {
  try {
    experiments.value = await api.listDLExperiments()
  } catch {
    /* fetch later when needed */
  }
})

onBeforeUnmount(() => {
  cancelled = true
  clearTimer()
})
</script>

<template>
  <section class="page">
    <!-- HERO -->
    <header class="hero">
      <div class="hero-accent" aria-hidden="true" />
      <div class="hero-inner">
        <span class="kicker">Corpus pipeline</span>
        <h2>Mine new AMD papers from PubMed</h2>
        <p class="lead">
          Pull recent abstracts, let an LLM agent extract new entities and relations, and review
          every change before it enters the ontology.
        </p>
        <div class="hero-links">
          <button type="button" class="hero-link" @click="toggleApproved">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M9 11l3 3L22 4" />
              <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
            </svg>
            {{ approvedOpen ? 'Hide previously approved papers' : 'View previously approved papers' }}
          </button>
          <button type="button" class="hero-link" @click="toggleRejected">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M6 6l1 14a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-14" />
            </svg>
            {{ rejectedOpen ? 'Hide previously rejected papers' : 'View previously rejected papers' }}
          </button>
        </div>
      </div>
    </header>

    <!-- APPROVED LITERATURE drawer -->
    <article v-if="approvedOpen" class="rejected-card">
      <header class="rejected-head">
        <div>
          <span class="kicker">Approved literature</span>
          <h3>Papers you've already approved</h3>
          <p>Read-only history of papers that passed your review and were sent through the pipeline.</p>
        </div>
        <button type="button" class="btn ghost" @click="loadApproved" :disabled="approvedLoading">
          {{ approvedLoading ? 'Loading…' : 'Refresh' }}
        </button>
      </header>

      <p v-if="approvedError" class="error">
        <span class="error-icon">!</span>{{ approvedError }}
      </p>

      <div v-if="approvedLoading" class="empty">Loading approved papers…</div>
      <div v-else-if="!approvedItems.length" class="empty">No approved papers yet. Anything you accept appears here.</div>

      <div v-else class="rejected-list">
        <article v-for="r in approvedItems" :key="r.pmid" class="rejected-item approved-item">
          <div class="rejected-body">
            <div class="rejected-meta">
              <span v-if="r.pmid" class="pmid">PMID {{ r.pmid }}</span>
              <span v-if="r.relevance" :class="['rel-pill', `rel-${String(r.relevance).toLowerCase()}`]">{{ r.relevance }}</span>
              <span v-if="r.approved_at" class="rejected-date">approved {{ r.approved_at }}</span>
              <span v-if="r.processed" class="processed-tag">processed</span>
            </div>
            <div class="rejected-title">{{ r.title || 'Untitled' }}</div>
            <p v-if="r.reason" class="rejected-reason">{{ r.reason }}</p>
            <details v-if="r.abstract_text || r.abstract" class="prop-abstract">
              <summary>Read abstract</summary>
              <p>{{ r.abstract_text || r.abstract }}</p>
            </details>
          </div>
        </article>
      </div>
    </article>

    <!-- REJECTED LITERATURE drawer -->
    <article v-if="rejectedOpen" class="rejected-card">
      <header class="rejected-head">
        <div>
          <span class="kicker">Rejected literature</span>
          <h3>Papers you previously declined</h3>
          <p>Restore any to put them back in the queue. They will appear in your next mining round.</p>
        </div>
        <button type="button" class="btn ghost" @click="loadRejected" :disabled="rejectedLoading">
          {{ rejectedLoading ? 'Loading…' : 'Refresh' }}
        </button>
      </header>

      <p v-if="rejectedError" class="error">
        <span class="error-icon">!</span>{{ rejectedError }}
      </p>

      <div v-if="rejectedLoading" class="empty">Loading rejected papers…</div>
      <div v-else-if="!rejectedItems.length" class="empty">No rejected papers. Anything you decline appears here.</div>

      <template v-else>
        <div class="prop-toolbar">
          <span class="prop-count">
            <strong>{{ selectedRejectedPmids.size }}</strong>
            of {{ rejectedItems.length }} selected
          </span>
          <div class="prop-bulk">
            <button type="button" class="micro" @click="selectAllRejected">Select all</button>
            <button type="button" class="micro" @click="clearRejectedSelection">Clear selection</button>
          </div>
        </div>

        <div class="rejected-list">
          <label
            v-for="r in rejectedItems"
            :key="r.pmid"
            class="rejected-item"
            :class="{ picked: selectedRejectedPmids.has(String(r.pmid)) }"
          >
            <input
              type="checkbox"
              :checked="selectedRejectedPmids.has(String(r.pmid))"
              :disabled="!r.pmid || bulkRestoring"
              @change="toggleRejectedPmid(r.pmid)"
            />
            <div class="rejected-body">
              <div class="rejected-meta">
                <span v-if="r.pmid" class="pmid">PMID {{ r.pmid }}</span>
                <span v-if="r.relevance" :class="['rel-pill', `rel-${String(r.relevance).toLowerCase()}`]">{{ r.relevance }}</span>
                <span v-if="r.rejected_at" class="rejected-date">rejected {{ r.rejected_at }}</span>
              </div>
              <div class="rejected-title">{{ r.title || 'Untitled' }}</div>
              <p v-if="r.reason" class="rejected-reason">{{ r.reason }}</p>
              <details v-if="r.abstract_text || r.abstract" class="prop-abstract" @click.stop>
                <summary @click.stop>Read abstract</summary>
                <p>{{ r.abstract_text || r.abstract }}</p>
              </details>
            </div>
            <button
              type="button"
              class="btn small ghost"
              :disabled="restoringPmids.has(String(r.pmid)) || bulkRestoring"
              @click.stop.prevent="restoreRejected(r.pmid)"
            >
              {{ restoringPmids.has(String(r.pmid)) ? 'Restoring…' : 'Restore one' }}
            </button>
          </label>
        </div>

        <footer class="approval-bar">
          <button type="button" class="btn ghost" @click="rejectedOpen = false">Close</button>
          <button
            type="button"
            class="btn primary lg"
            :disabled="selectedRejectedPmids.size === 0 || bulkRestoring"
            @click="restoreSelectedRejected"
          >
            {{ bulkRestoring ? 'Restoring…' : `Restore ${selectedRejectedPmids.size} selected` }}
            <span class="arrow">→</span>
          </button>
        </footer>
      </template>
    </article>

    <!-- HOW IT WORKS -->
    <section class="how">
      <header class="how-head">
        <span class="how-eyebrow">How it works</span>
        <span class="how-meta">5 steps · 2 of them are yours</span>
      </header>
      <ol class="how-steps">
        <li v-for="(s, i) in HOW_IT_WORKS" :key="s.num" :class="['how-card', `actor-${s.actor}`]" :style="{ animationDelay: `${i * 80}ms` }">
          <div class="how-icon">
            <svg v-if="s.icon === 'search'" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="11" cy="11" r="7" /><path d="M16 16l5 5" />
            </svg>
            <svg v-else-if="s.icon === 'check'" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
            </svg>
            <svg v-else-if="s.icon === 'sparkle'" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1" /><circle cx="12" cy="12" r="3" />
            </svg>
            <svg v-else-if="s.icon === 'eye'" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z" /><circle cx="12" cy="12" r="3" />
            </svg>
            <svg v-else-if="s.icon === 'shield'" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 3l8 4v5c0 5-3.5 8.5-8 9-4.5-.5-8-4-8-9V7z" /><path d="M9 12l2 2 4-4" />
            </svg>
          </div>
          <div class="how-text">
            <div class="how-step-row">
              <span class="how-num">{{ s.num }}</span>
              <span class="how-tag">{{ s.actor === 'human' ? 'You' : 'Auto' }}</span>
            </div>
            <div class="how-step-title">{{ s.title }}</div>
            <div class="how-step-body">{{ s.body }}</div>
          </div>
        </li>
      </ol>
    </section>

    <!-- CONFIGURE -->
    <article class="config-card" v-if="!pipelineActive && !pipelineDone && !awaitingApproval && !awaitingMiningReview && !pipelineError">
      <header class="card-header">
        <div class="card-header-text">
          <h3>Configure your run</h3>
          <p>Defaults are sensible — most users only change the date range.</p>
        </div>
        <div class="card-header-meta">
          <span class="meta-num">{{ plannedSteps.length }}</span>
          <span class="meta-lbl">steps planned</span>
        </div>
      </header>

      <form @submit.prevent="startPipeline" class="form">
        <!-- DAYS field -->
        <div class="field big-field">
          <div class="field-head">
            <label class="lbl" for="days">
              <span class="lbl-num">1</span>
              How far back to search?
            </label>
            <span class="value-pill">
              <strong>{{ days }}</strong>
              {{ days === 1 ? 'day' : 'days' }}
            </span>
          </div>
          <p class="help">PubMed will return AMD papers published within this window.</p>
          <div class="slider-row">
            <input
              id="days"
              v-model.number="days"
              type="range"
              min="1"
              max="365"
              step="1"
              class="slider"
              :style="{ '--pct': `${(days / 365) * 100}%` }"
            />
            <input
              v-model.number="days"
              type="number"
              min="1"
              max="3650"
              class="num-input"
              aria-label="Days"
            />
          </div>
          <div class="presets">
            <button v-for="p in [7, 30, 90, 365]" :key="p" type="button" class="preset" :class="{ on: days === p }" @click="days = p">
              {{ p === 7 ? 'Last week' : p === 30 ? 'Last month' : p === 90 ? 'Last 3 months' : 'Last year' }}
            </button>
          </div>
        </div>

        <!-- MODEL field -->
        <div class="field big-field">
          <div class="field-head">
            <label class="lbl">
              <span class="lbl-num">2</span>
              Which model should extract entities?
            </label>
          </div>
          <p class="help">Cloud models (Groq) are faster and higher quality. Local models (Ollama) keep data on your machine.</p>
          <ModelSelector v-model="model" label="" />
        </div>

        <details class="advanced" :open="showAdvanced" @toggle="showAdvanced = $event.target.open">
          <summary>
            <span class="adv-summary">
              <span>Advanced options</span>
              <span class="adv-hint">{{ showAdvanced ? 'hide' : 'show' }}</span>
            </span>
          </summary>
          <div class="adv-body">
            <label class="opt-card" :class="{ on: runValidation }">
              <input type="checkbox" v-model="runValidation" />
              <div class="opt-text">
                <div class="opt-title">Validation agent <span class="rec">recommended</span></div>
                <div class="opt-body">A second agent reviews the ontology after mining and proposes fixes you can approve or reject.</div>
              </div>
              <div v-if="runValidation" class="opt-extra" @click.stop>
                <label class="lbl-inline" for="passes">Passes</label>
                <input id="passes" v-model.number="validationPasses" type="number" min="1" max="5" class="num-input small" />
              </div>
            </label>

            <label class="opt-card" :class="{ on: runHermit }">
              <input type="checkbox" v-model="runHermit" />
              <div class="opt-text">
                <div class="opt-title">HermiT reasoner</div>
                <div class="opt-body">Classify the ontology, check consistency and surface inferred axioms — same engine Protégé uses.</div>
              </div>
            </label>

            <label class="opt-card" :class="{ on: runDLLearner }">
              <input type="checkbox" v-model="runDLLearner" />
              <div class="opt-text">
                <div class="opt-title">DL-Learner experiment</div>
                <div class="opt-body">Run a description-logic learning experiment on the resulting OWL. Returns a ranked list of class expressions.</div>
                <select v-if="runDLLearner" v-model="dllExperiment" class="exp-select" @click.stop>
                  <option v-if="!experiments.length" value="">Loading experiments…</option>
                  <option v-for="e in experiments" :key="e.name" :value="e.name">
                    {{ e.title || e.name }}
                  </option>
                </select>
              </div>
            </label>
          </div>
        </details>

        <div class="cta-row">
          <button type="submit" class="btn primary xl" :disabled="!model">
            <span class="cta-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M5 3l14 9-14 9z" />
              </svg>
            </span>
            Start the pipeline
            <span class="arrow">→</span>
          </button>
          <div class="planned-summary">
            <div class="planned-line">
              <strong>{{ plannedSteps.length }}</strong> steps planned
            </div>
            <div class="planned-sub">Pauses twice for your input</div>
          </div>
        </div>

        <p v-if="pipelineError" class="error">
          <span class="error-icon">!</span>{{ pipelineError }}
        </p>
      </form>
    </article>

    <!-- ====== Step rail (shown once pipeline starts) ====== -->
    <ol v-if="pipelineActive || pipelineDone || awaitingApproval || awaitingMiningReview || pipelineError" class="rail">
      <li v-for="s in plannedSteps" :key="s.key" :class="['rail-item', stepStatus(s.key)]">
        <span class="rail-dot">
          <svg v-if="stepStatus(s.key) === 'done'" viewBox="0 0 12 12" width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 6.5l2 2 4-5" />
          </svg>
          <span v-else-if="stepStatus(s.key) === 'active'" class="rail-spin" />
          <span v-else class="rail-num">{{ String(plannedSteps.indexOf(s) + 1).padStart(2, '0') }}</span>
        </span>
        <span class="rail-lbl">{{ s.label }}</span>
      </li>
    </ol>

    <!-- ====== Observe ====== -->
    <article v-if="(pipelineActive || pipelineDone || awaitingApproval || awaitingMiningReview || pipelineError) && overallLog.length" class="step">
      <header class="step-head">
        <span class="step-num">·</span>
        <div>
          <h3>Progress</h3>
          <p>Live updates from each step. Pauses are highlighted.</p>
        </div>
      </header>

      <div class="step-body">
        <div class="overall-row">
          <span :class="['badge', pipelineDone ? 'badge-done' : pipelineError ? 'badge-error' : awaitingApproval || awaitingMiningReview || awaitingValidationReview ? 'badge-paused' : 'badge-running']">
            <span class="badge-dot" />
            {{ pipelineDone ? 'done' : pipelineError ? 'error' : awaitingApproval || awaitingMiningReview || awaitingValidationReview ? 'waiting on you' : 'running' }}
          </span>
          <span v-if="currentStep" class="now">
            Now: <strong>{{ plannedSteps.find((s) => s.key === currentStep)?.label }}</strong>
          </span>
          <span class="pct">{{ overallPct }}%</span>
          <button v-if="pipelineActive" type="button" class="btn small ghost" @click="cancelPipeline">Cancel</button>
        </div>

        <div class="progress">
          <div class="progress-track">
            <div class="progress-fill" :style="{ width: `${overallPct}%` }" />
          </div>
        </div>

        <div class="logs">
          <header class="logs-head">
            <span>./pipeline · log</span>
            <span>{{ overallLog.length }} lines</span>
          </header>
          <pre>{{ overallLog.join('\n') }}</pre>
        </div>
      </div>
    </article>

    <!-- ====== PubMed proposal review ====== -->
    <article
      v-if="litResult && awaitingApproval"
      class="step gate-step"
    >
      <header class="step-head">
        <span class="step-num gate">★</span>
        <div>
          <h3>{{ awaitingApproval ? 'Pick papers to mine' : 'Picked papers' }}</h3>
          <p v-if="awaitingApproval">
            {{ litResult.proposals?.length || 0 }} papers came back. Tick the ones worth mining —
            <strong class="ok">relevant</strong> ones are pre-selected, <strong class="warn-text">borderline</strong>
            ones are shown but unticked. The agent already filtered out anything it judged not relevant.
          </p>
          <p v-else>{{ approveResult?.saved?.length || 0 }} paper{{ approveResult?.saved?.length === 1 ? '' : 's' }} saved.</p>
        </div>
      </header>

      <div class="step-body">
        <template v-if="litResult.proposals?.length">
          <div v-if="awaitingApproval" class="prop-toolbar">
            <span class="prop-count">
              <strong>{{ selectedPmids.size }}</strong>
              of {{ litResult.proposals.length }} selected
            </span>
            <div class="prop-bulk">
              <button type="button" class="micro" @click="selectAllProposals">Select every paper</button>
              <button type="button" class="micro" @click="clearProposalSelection">Clear selection</button>
            </div>
          </div>

          <div class="prop-list">
            <label
              v-for="(p, i) in litResult.proposals"
              :key="p.pmid || i"
              class="prop"
              :class="{ picked: selectedPmids.has(String(p.pmid)), disabled: !awaitingApproval }"
            >
              <input
                type="checkbox"
                :checked="selectedPmids.has(String(p.pmid))"
                :disabled="!awaitingApproval || !p.pmid"
                @change="togglePmid(p.pmid)"
              />
              <div class="prop-body">
                <div class="prop-head">
                  <span v-if="p.pmid" class="pmid">PMID {{ p.pmid }}</span>
                  <span v-if="p.relevance" :class="['rel-pill', `rel-${String(p.relevance).toLowerCase()}`]">{{ p.relevance }}</span>
                  <span v-if="p.year" class="year">{{ p.year }}</span>
                </div>
                <div class="prop-title">{{ p.title || 'Untitled' }}</div>
                <p v-if="p.reason" class="prop-reason">{{ p.reason }}</p>
                <details v-if="p.abstract_text || p.abstract" class="prop-abstract">
                  <summary>Read abstract</summary>
                  <p>{{ p.abstract_text || p.abstract }}</p>
                </details>
              </div>
            </label>
          </div>

          <footer v-if="awaitingApproval" class="approval-bar">
            <button type="button" class="btn ghost" @click="cancelPipeline">Cancel</button>
            <button type="button" class="btn primary lg" :disabled="selectedPmids.size === 0" @click="continueAfterApproval">
              Mine {{ selectedPmids.size }} selected
              <span class="arrow">→</span>
            </button>
          </footer>

          <div v-else-if="approveResult" class="approve-summary">
            <span class="ok">✓ {{ approveResult.saved?.length || 0 }} saved</span>
            <span v-if="approveResult.skipped_missing_text?.length" class="warn">
              {{ approveResult.skipped_missing_text.length }} skipped
            </span>
          </div>
        </template>
        <div v-else class="empty">PubMed returned no papers in this date range. Try a wider window.</div>
      </div>
    </article>

    <!-- ====== Mining additions review ====== -->
    <article
      v-if="miningChanges && awaitingMiningReview"
      class="step gate-step"
    >
      <header class="step-head">
        <span class="step-num gate">★</span>
        <div>
          <h3>{{ awaitingMiningReview ? 'Confirm what was extracted' : 'Confirmed' }}</h3>
          <p v-if="awaitingMiningReview">
            The agent added the items below. Untick anything that doesn't belong, then continue —
            validation runs next.
          </p>
          <p v-else>{{ keptCount }} of {{ miningChanges.newInstances.length }} instances kept.</p>
        </div>
      </header>

      <div class="step-body">
        <div class="diff-stats">
          <div>
            <div class="diff-stat-num">{{ miningChanges.newClasses.length }}</div>
            <div class="diff-stat-lbl">new classes</div>
          </div>
          <div>
            <div class="diff-stat-num">{{ miningChanges.newInstances.length }}</div>
            <div class="diff-stat-lbl">new instances</div>
          </div>
          <div>
            <div class="diff-stat-num">{{ miningChanges.newTriples.length }}</div>
            <div class="diff-stat-lbl">new relationships</div>
          </div>
        </div>

        <div v-if="!miningChanges.newClasses.length && !miningChanges.newInstances.length && !miningChanges.newTriples.length" class="empty">
          The agent did not add anything new. Continue to validation.
        </div>

        <section v-if="miningChanges.newClasses.length" class="diff-block">
          <header class="diff-head">
            <h4>New classes</h4>
            <span class="diff-count">{{ miningChanges.newClasses.length }}</span>
          </header>
          <div class="diff-chips">
            <span v-for="c in miningChanges.newClasses" :key="c" class="diff-chip class-chip">{{ c }}</span>
          </div>
        </section>

        <section v-if="miningChanges.newInstances.length" class="diff-block">
          <header class="diff-head">
            <h4>New instances</h4>
            <span class="diff-count">{{ miningChanges.newInstances.length }}</span>
            <div v-if="awaitingMiningReview" class="prop-bulk">
              <button type="button" class="micro" @click="keepAllInstances">Keep all</button>
              <button type="button" class="micro" @click="removeAllInstances">Remove all</button>
            </div>
          </header>

          <div v-for="[type, items] in groupedNewInstances" :key="type" class="entity-group">
            <span class="group-label">{{ type }} <span class="group-count">· {{ items.length }}</span></span>
            <div class="diff-rows">
              <label
                v-for="i in items"
                :key="i.name"
                class="diff-row"
                :class="{ removed: instancesToRemove.has(i.name), disabled: !awaitingMiningReview }"
              >
                <input
                  type="checkbox"
                  :checked="!instancesToRemove.has(i.name)"
                  :disabled="!awaitingMiningReview"
                  @change="toggleInstanceRemoval(i.name)"
                />
                <span class="diff-name" :class="{ strike: instancesToRemove.has(i.name) }">{{ i.name }}</span>
              </label>
            </div>
          </div>
        </section>

        <section v-if="miningChanges.newTriples.length" class="diff-block">
          <header class="diff-head">
            <h4>New relationships</h4>
            <span class="diff-count">{{ miningChanges.newTriples.length }}</span>
          </header>
          <details class="triples-details">
            <summary>Show relationships</summary>
            <ul class="triple-list">
              <li v-for="(t, i) in miningChanges.newTriples" :key="i" class="triple-row">
                <span class="triple-s">{{ t.subject }}</span>
                <span class="triple-p">{{ t.predicate }}</span>
                <span class="triple-o">{{ t.object }}</span>
              </li>
            </ul>
          </details>
        </section>

        <footer v-if="awaitingMiningReview" class="approval-bar">
          <button type="button" class="btn ghost" @click="cancelPipeline">Cancel</button>
          <button type="button" class="btn primary lg" @click="confirmMiningChanges">
            <template v-if="instancesToRemove.size">
              Remove {{ instancesToRemove.size }} &amp; continue to validation
            </template>
            <template v-else>
              Looks good, continue to validation
            </template>
            <span class="arrow">→</span>
          </button>
        </footer>
      </div>
    </article>

    <!-- ====== Validation review ====== -->
    <article v-if="fixes.length" class="step gate-step">
      <header class="step-head">
        <span class="step-num gate">★</span>
        <div>
          <h3>Validation suggested fixes</h3>
          <p>The validation agent proposed {{ fixes.length }} change{{ fixes.length === 1 ? '' : 's' }}. Approve what looks right.</p>
        </div>
      </header>

      <div class="step-body">
        <div class="fixes">
          <article v-for="(fix, i) in fixes" :key="fix.fix_id ?? fix.id" class="fix">
            <span class="fix-num">{{ String(i + 1).padStart(2, '0') }}</span>
            <div class="fix-body">
              <span v-if="fix.kind || fix.type" class="fix-tag">{{ fix.kind || fix.type }}</span>
              <p>{{ fixSummary(fix) }}</p>
              <details v-if="fix.before || fix.after || fix.diff" class="raw">
                <summary>Detail</summary>
                <pre>{{ JSON.stringify(fix, null, 2) }}</pre>
              </details>
            </div>
            <div class="fix-actions">
              <span v-if="decided[fix.fix_id ?? fix.id]" :class="['decided', decided[fix.fix_id ?? fix.id]]">
                {{ decided[fix.fix_id ?? fix.id] }}
              </span>
              <template v-else>
                <button class="btn small approve" type="button" @click="decide(fix, 'approve')">Approve</button>
                <button class="btn small reject" type="button" @click="decide(fix, 'reject')">Reject</button>
              </template>
            </div>
          </article>
        </div>
      </div>

      <footer v-if="awaitingValidationReview" class="approval-bar">
        <button type="button" class="btn ghost" @click="cancelPipeline">Cancel</button>
        <button type="button" class="btn primary lg" @click="continueAfterValidation">
          Continue to HermiT / DL-Learner
          <span class="arrow">→</span>
        </button>
      </footer>
    </article>

    <!-- ====== HermiT result ====== -->
    <article v-if="hermitResult" class="step">
      <header class="step-head">
        <span class="step-num">·</span>
        <div>
          <h3>HermiT reasoner</h3>
          <p>
            Ontology is
            <strong v-if="hermitResult.consistent === false" class="bad">inconsistent</strong>
            <strong v-else class="good">consistent</strong>.
            {{ hermitResult.inferred_axioms?.length || 0 }} inferred axiom{{ hermitResult.inferred_axioms?.length === 1 ? '' : 's' }}.
          </p>
        </div>
      </header>
      <div class="step-body">
        <section v-if="hermitResult.unsatisfiable_classes?.length" class="diff-block">
          <header class="diff-head">
            <h4>Unsatisfiable classes</h4>
            <span class="diff-count">{{ hermitResult.unsatisfiable_classes.length }}</span>
          </header>
          <div class="diff-chips">
            <span v-for="c in hermitResult.unsatisfiable_classes" :key="c" class="diff-chip" style="background: var(--danger-soft); color: var(--danger); border: 1px solid #f5c6cb;">{{ c }}</span>
          </div>
        </section>

        <section v-if="hermitResult.inferred_axioms?.length" class="diff-block">
          <header class="diff-head">
            <h4>Inferred axioms</h4>
            <span class="diff-count">{{ hermitResult.inferred_axioms.length }}</span>
          </header>
          <ul class="solutions">
            <li v-for="(ax, i) in hermitResult.inferred_axioms.slice(0, 30)" :key="i" class="solution">
              <span class="rank">{{ String(i + 1).padStart(2, '0') }}</span>
              <div class="sol-body">
                <code>{{ typeof ax === 'string' ? ax : (ax.expression || ax.axiom || JSON.stringify(ax)) }}</code>
              </div>
            </li>
          </ul>
          <p v-if="hermitResult.inferred_axioms.length > 30" class="caption">
            Showing 30 of {{ hermitResult.inferred_axioms.length }} inferred axioms.
          </p>
        </section>

        <details v-if="hermitResult.raw_output" class="raw">
          <summary>Raw HermiT output</summary>
          <pre>{{ hermitResult.raw_output }}</pre>
        </details>
      </div>
    </article>

    <!-- ====== DL-Learner result ====== -->
    <article v-if="dlResult" class="step">
      <header class="step-head">
        <span class="step-num">·</span>
        <div>
          <h3>DL-Learner result</h3>
          <p>Top class expressions for <strong>{{ experiments.find((e) => e.name === dllExperiment)?.title || dllExperiment }}</strong>.</p>
        </div>
      </header>
      <div class="step-body">
        <ol v-if="dlResult.solutions?.length" class="solutions">
          <li v-for="(s, i) in dlResult.solutions.slice(0, 10)" :key="i" class="solution">
            <span class="rank">{{ String(i + 1).padStart(2, '0') }}</span>
            <div class="sol-body">
              <code>{{ s.expression || s.description || s }}</code>
              <div v-if="s.accuracy != null || s.score != null" class="sol-meta">
                <span v-if="s.accuracy != null">acc <strong>{{ Number(s.accuracy).toFixed(3) }}</strong></span>
                <span v-if="s.score != null">score <strong>{{ Number(s.score).toFixed(3) }}</strong></span>
              </div>
            </div>
          </li>
        </ol>
        <div v-else class="empty">No solutions returned.</div>
      </div>
    </article>

    <!-- DONE banner -->
    <article v-if="pipelineDone" class="done-banner">
      <div class="done-icon">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M5 13l4 4L19 7" />
        </svg>
      </div>
      <div class="done-body">
        <h4>Pipeline complete</h4>
        <p>Open the Graph tab to inspect the updated ontology, or run another batch.</p>
      </div>
      <button type="button" class="btn ghost" @click="resetPipelineState(); pipelineDone = false; overallLog = []">
        Run another
      </button>
    </article>
  </section>
</template>


<style scoped>
/* Corpus Extraction — professional medical, calm and spacious */

.page {
  max-width: 1320px;
  margin: 0 auto;
  padding: var(--s-6) var(--s-6) var(--s-9);
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
  animation: fade-up 320ms var(--ease) both;
}

/* Hero */
.hero {
  position: relative;
  padding: var(--s-6) var(--s-6) var(--s-6) calc(var(--s-6) + 6px);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  overflow: hidden;
}

.hero-accent {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 6px;
  background: var(--brand);
}

.hero-inner {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}

.kicker {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--brand);
}

.hero h2 {
  font-size: var(--t-2xl);
  font-weight: 600;
  letter-spacing: -0.02em;
  color: var(--text);
  line-height: 1.15;
  max-width: 22ch;
}

.lead {
  font-size: var(--t-md);
  color: var(--text-soft);
  max-width: 64ch;
  line-height: 1.65;
}

.hero-links {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-5);
  margin-top: var(--s-3);
}

.hero-link {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  padding: 8px 0;
  font-size: var(--t-sm);
  font-weight: 500;
  color: var(--brand);
  border-bottom: 1px solid transparent;
  transition: border-color var(--speed) var(--ease);
}

.hero-link:hover {
  border-bottom-color: var(--brand);
}

/* Rejected literature drawer */
.rejected-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  padding: var(--s-6);
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
  animation: fade-up 280ms var(--ease) both;
}

.rejected-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--s-4);
  padding-bottom: var(--s-4);
  border-bottom: 1px solid var(--border);
}

.rejected-head h3 {
  font-size: var(--t-xl);
  font-weight: 600;
  letter-spacing: -0.02em;
  color: var(--text);
  margin-top: var(--s-2);
}

.rejected-head p {
  font-size: var(--t-sm);
  color: var(--text-muted);
  margin-top: var(--s-2);
  max-width: 60ch;
  line-height: 1.6;
}

.rejected-list {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}

.rejected-item {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: var(--s-4);
  padding: var(--s-4);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  align-items: flex-start;
  cursor: pointer;
  transition: border-color var(--speed) var(--ease), background var(--speed) var(--ease);
}

.rejected-item:hover {
  border-color: var(--text-muted);
}

.rejected-item.picked {
  border-color: var(--brand);
  background: var(--brand-tint);
}

.rejected-item input[type='checkbox'] {
  margin-top: 4px;
  accent-color: var(--brand);
  width: 18px;
  height: 18px;
  cursor: pointer;
  flex-shrink: 0;
}

.approved-item {
  grid-template-columns: 1fr;
  cursor: default;
}

.approved-item:hover {
  border-color: var(--border);
}

.processed-tag {
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding: 3px var(--s-2);
  border-radius: var(--r-sm);
  background: var(--success-soft);
  color: var(--success);
  border: 1px solid #c5ecd0;
}

.rejected-body {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  min-width: 0;
}

.rejected-meta {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  flex-wrap: wrap;
}

.rejected-date {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-faint);
}

.rejected-title {
  font-size: var(--t-md);
  font-weight: 600;
  color: var(--text);
  line-height: 1.45;
}

.rejected-reason {
  font-size: 13px;
  color: var(--text-soft);
  font-style: italic;
  line-height: 1.6;
}

/* How it works */
.how {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}

.how-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding-bottom: var(--s-3);
  border-bottom: 1px solid var(--border);
}

.how-eyebrow {
  font-size: var(--t-sm);
  font-weight: 600;
  color: var(--text);
}

.how-meta {
  font-size: 12px;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.how-steps {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: var(--s-3);
  list-style: none;
}

.how-card {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  padding: var(--s-4);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  opacity: 0;
  animation: fade-up 360ms var(--ease) both;
  transition: border-color var(--speed) var(--ease);
}

.how-card:hover {
  border-color: var(--brand);
}

.how-icon {
  width: 40px;
  height: 40px;
  border-radius: var(--r-sm);
  background: var(--brand-soft);
  color: var(--brand);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.how-text {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.how-step-row {
  display: flex;
  align-items: center;
  gap: var(--s-2);
}

.how-num {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  letter-spacing: 0.04em;
}

.how-tag {
  font-family: var(--font-mono);
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding: 2px 6px;
  border-radius: var(--r-sm);
  color: var(--text-muted);
  background: var(--bg-tint);
  border: 1px solid var(--border);
}

.how-card.actor-human .how-tag {
  color: var(--brand);
  background: var(--brand-soft);
  border-color: color-mix(in srgb, var(--brand) 20%, transparent);
}

.how-step-title {
  font-size: var(--t-sm);
  font-weight: 600;
  color: var(--text);
}

.how-step-body {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.55;
}

/* Configure card */
.config-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  padding: var(--s-6);
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--s-4);
  padding-bottom: var(--s-4);
  border-bottom: 1px solid var(--border);
}

.card-header-text h3 {
  font-size: var(--t-xl);
  font-weight: 600;
  letter-spacing: -0.02em;
  color: var(--text);
}

.card-header-text p {
  font-size: var(--t-sm);
  color: var(--text-muted);
  margin-top: var(--s-2);
  max-width: 50ch;
}

.card-header-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  flex-shrink: 0;
}

.meta-num {
  font-family: var(--font-mono);
  font-size: var(--t-xl);
  font-weight: 600;
  color: var(--brand);
  line-height: 1;
}

.meta-lbl {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
}

.form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--s-4);
}

.form > .advanced,
.form > .cta-row,
.form > .error {
  grid-column: 1 / -1;
}

.field {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}

.big-field {
  padding: var(--s-5);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
}

.field-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--s-4);
}

.lbl {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  font-size: var(--t-md);
  font-weight: 600;
  color: var(--text);
}

.lbl-num {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: var(--brand);
  color: white;
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.value-pill {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-muted);
  background: var(--surface);
  padding: 6px var(--s-3);
  border-radius: var(--r-sm);
  border: 1px solid var(--border);
}

.value-pill strong {
  color: var(--brand);
  font-weight: 700;
  font-size: 14px;
  margin-right: 4px;
}

.help {
  font-size: var(--t-sm);
  color: var(--text-muted);
  line-height: 1.55;
  margin-top: var(--s-1);
}

.slider-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: var(--s-4);
  align-items: center;
  margin-top: var(--s-3);
}

.slider {
  appearance: none;
  -webkit-appearance: none;
  width: 100%;
  height: 6px;
  background: linear-gradient(to right, var(--brand) 0%, var(--brand) var(--pct, 0%), var(--bg-tint) var(--pct, 0%), var(--bg-tint) 100%);
  border-radius: var(--r-pill);
  outline: none;
}

.slider::-webkit-slider-thumb {
  appearance: none;
  width: 22px;
  height: 22px;
  background: white;
  border-radius: 50%;
  cursor: pointer;
  border: 2px solid var(--brand);
  box-shadow: var(--shadow-sm);
}

.slider::-moz-range-thumb {
  width: 22px;
  height: 22px;
  background: white;
  border-radius: 50%;
  cursor: pointer;
  border: 2px solid var(--brand);
  box-shadow: var(--shadow-sm);
}

.num-input {
  width: 90px;
  padding: var(--s-3);
  font-family: var(--font);
  font-size: var(--t-sm);
  text-align: center;
  color: var(--text);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  outline: none;
  transition: border-color var(--speed) var(--ease);
}

.num-input:focus {
  border-color: var(--brand);
}

.num-input.small {
  width: 76px;
  padding: 8px var(--s-2);
}

.presets {
  display: flex;
  gap: var(--s-2);
  flex-wrap: wrap;
  margin-top: var(--s-3);
}

.preset {
  padding: 8px var(--s-3);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  font-size: 13px;
  color: var(--text-soft);
  font-weight: 500;
  transition: border-color var(--speed) var(--ease), color var(--speed) var(--ease);
}

.preset:hover {
  border-color: var(--brand);
  color: var(--brand);
}

.preset.on {
  background: var(--brand-soft);
  color: var(--brand);
  border-color: var(--brand);
  font-weight: 600;
}

/* Advanced */
.advanced {
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface);
  overflow: hidden;
}

.advanced summary {
  padding: var(--s-4) var(--s-5);
  cursor: pointer;
  user-select: none;
  list-style: none;
}

.advanced summary::-webkit-details-marker {
  display: none;
}

.adv-summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: var(--t-sm);
  font-weight: 600;
  color: var(--text);
}

.adv-hint {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--brand);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 600;
}

.adv-body {
  padding: var(--s-5);
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  background: var(--bg);
}

.opt-card {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: var(--s-4);
  padding: var(--s-4);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  cursor: pointer;
  align-items: start;
  transition: border-color var(--speed) var(--ease);
}

.opt-card.on {
  border-color: var(--brand);
}

.opt-card input[type='checkbox'] {
  margin-top: 2px;
  accent-color: var(--brand);
  width: 18px;
  height: 18px;
}

.opt-text {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.opt-title {
  font-size: var(--t-sm);
  font-weight: 600;
  color: var(--text);
  display: flex;
  align-items: center;
  gap: var(--s-2);
}

.rec {
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 2px 6px;
  background: var(--success-soft);
  color: var(--success);
  border-radius: var(--r-sm);
}

.opt-body {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.55;
  max-width: 60ch;
}

.opt-extra {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: flex-end;
}

.lbl-inline {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
}

.exp-select {
  margin-top: var(--s-2);
  width: 100%;
  padding: var(--s-3);
  font-family: var(--font);
  font-size: 13px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  color: var(--text);
  outline: none;
}

.exp-select:focus {
  border-color: var(--brand);
}

/* CTA */
.cta-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--s-5);
  padding-top: var(--s-5);
  border-top: 1px solid var(--border);
}

.cta-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  padding: var(--s-3) var(--s-4);
  border-radius: var(--r-sm);
  font-size: var(--t-sm);
  font-weight: 600;
  letter-spacing: -0.005em;
  transition: background var(--speed) var(--ease), color var(--speed) var(--ease), border-color var(--speed) var(--ease);
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
}

.btn.lg {
  padding: 12px var(--s-5);
  font-size: var(--t-md);
}

.btn.xl {
  padding: 16px var(--s-6);
  font-size: var(--t-md);
  font-weight: 600;
}

.btn.ghost {
  background: var(--surface);
  border: 1px solid var(--border);
  color: var(--text);
}

.btn.ghost:hover:not(:disabled) {
  border-color: var(--text-muted);
}

.btn.small {
  padding: 7px var(--s-3);
  font-size: 12px;
  font-weight: 500;
}

.btn.approve {
  background: var(--success);
  color: white;
}

.btn.approve:hover {
  background: #15803d;
}

.btn.reject {
  background: var(--surface);
  color: var(--danger);
  border: 1px solid var(--border);
}

.btn.reject:hover {
  border-color: var(--danger);
  background: var(--danger-soft);
}

.btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.planned-summary {
  text-align: right;
}

.planned-line {
  font-size: var(--t-sm);
  color: var(--text);
  font-weight: 500;
}

.planned-line strong {
  font-family: var(--font-mono);
  color: var(--brand);
  font-weight: 700;
  margin-right: 2px;
}

.planned-sub {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
}

.error {
  display: flex;
  gap: var(--s-3);
  align-items: center;
  font-size: var(--t-sm);
  color: var(--danger);
  background: var(--danger-soft);
  border: 1px solid #f5c6cb;
  padding: var(--s-4);
  border-radius: var(--r-sm);
  margin-top: var(--s-3);
}

.error-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--danger);
  color: white;
  font-size: 13px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

/* Step rail */
.rail {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  list-style: none;
  padding: var(--s-4) var(--s-5);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  overflow-x: auto;
}

.rail-item {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  padding: 4px var(--s-2);
  font-size: var(--t-sm);
  color: var(--text-muted);
  white-space: nowrap;
}

.rail-item + .rail-item::before {
  content: '';
  width: 28px;
  height: 1px;
  background: var(--border);
  margin-right: var(--s-2);
}

.rail-item.active {
  color: var(--brand);
  font-weight: 600;
}

.rail-item.done {
  color: var(--success);
  font-weight: 500;
}

.rail-dot {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 1.5px solid var(--border-strong);
  background: var(--surface);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 700;
  color: var(--text-faint);
  transition: all var(--speed) var(--ease);
}

.rail-num {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-faint);
}

.rail-item.active .rail-dot {
  border-color: var(--brand);
  background: var(--brand);
  color: white;
}

.rail-item.done .rail-dot {
  border-color: var(--success);
  background: var(--success);
  color: white;
}

.rail-spin {
  width: 10px;
  height: 10px;
  border: 1.5px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  display: inline-block;
  animation: spin 800ms linear infinite;
}

/* Step cards */
.step {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  padding: var(--s-6);
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
  animation: fade-up 280ms var(--ease) both;
}

.gate-step {
  border-left: 4px solid var(--brand);
}

.step-head {
  display: flex;
  gap: var(--s-4);
  align-items: flex-start;
  padding-bottom: var(--s-4);
  border-bottom: 1px solid var(--border);
}

.step-num {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--bg-tint);
  color: var(--text-muted);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-mono);
  font-size: var(--t-sm);
  font-weight: 600;
  flex-shrink: 0;
}

.step-num.gate {
  background: var(--brand);
  color: white;
  font-size: 16px;
}

.step-head h3 {
  font-size: var(--t-lg);
  font-weight: 600;
  letter-spacing: -0.015em;
  color: var(--text);
  line-height: 1.3;
}

.step-head p {
  font-size: var(--t-sm);
  color: var(--text-muted);
  margin-top: var(--s-2);
  line-height: 1.6;
  max-width: 60ch;
}

.step-body {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}

/* Observe */
.overall-row {
  display: flex;
  align-items: center;
  gap: var(--s-4);
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
  background: var(--bg-tint);
  color: var(--text-muted);
  border: 1px solid var(--border);
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
  border-color: color-mix(in srgb, var(--brand) 25%, transparent);
}

.badge-running .badge-dot {
  animation: pulse 1.4s var(--ease) infinite;
}

.badge-paused {
  background: var(--warning-soft);
  color: var(--warning);
  border-color: #fad8a3;
}

.badge-done {
  background: var(--success-soft);
  color: var(--success);
  border-color: #c5ecd0;
}

.badge-error {
  background: var(--danger-soft);
  color: var(--danger);
  border-color: #f5c6cb;
}

.now {
  font-size: var(--t-sm);
  color: var(--text-muted);
}

.now strong {
  color: var(--text);
  font-weight: 600;
}

.pct {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: var(--t-md);
  font-weight: 600;
  color: var(--text);
}

.progress {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.progress-track {
  height: 6px;
  background: var(--bg-tint);
  border-radius: var(--r-pill);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--brand);
  border-radius: var(--r-pill);
  transition: width 380ms var(--ease);
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
  padding: var(--s-3) var(--s-4);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #8b97a8;
  border-bottom: 1px solid #1f2a3c;
}

.logs pre {
  padding: var(--s-4);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 320px;
  overflow: auto;
}

/* PubMed proposals */
.prop-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--s-3) var(--s-4);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  font-size: var(--t-sm);
}

.prop-count {
  color: var(--text-soft);
}

.prop-count strong {
  color: var(--brand);
  font-weight: 700;
  font-family: var(--font-mono);
}

.prop-bulk {
  display: flex;
  gap: var(--s-2);
}

.micro {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 6px var(--s-3);
  border-radius: var(--r-sm);
  color: var(--text-muted);
  background: var(--surface);
  border: 1px solid var(--border);
  transition: all var(--speed) var(--ease);
}

.micro:hover {
  color: var(--brand);
  border-color: var(--brand);
}

.prop-list {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}

.prop {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--s-4);
  padding: var(--s-4);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  cursor: pointer;
  transition: border-color var(--speed) var(--ease), background var(--speed) var(--ease);
  align-items: flex-start;
}

.prop:hover:not(.disabled) {
  border-color: var(--text-muted);
}

.prop.picked {
  border-color: var(--brand);
  background: var(--brand-tint);
}

.prop.disabled {
  opacity: 0.7;
  cursor: default;
}

.prop input[type='checkbox'] {
  margin-top: 4px;
  accent-color: var(--brand);
  width: 18px;
  height: 18px;
  cursor: pointer;
}

.prop-body {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  min-width: 0;
}

.prop-head {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  flex-wrap: wrap;
}

.pmid {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  background: var(--bg-tint);
  color: var(--text-muted);
  padding: 3px var(--s-2);
  border-radius: var(--r-sm);
}

.year {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-faint);
}

.rel-pill {
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding: 3px var(--s-2);
  border-radius: var(--r-sm);
  border: 1px solid;
}

.rel-high,
.rel-relevant {
  color: var(--success);
  background: var(--success-soft);
  border-color: #c5ecd0;
}

.rel-medium,
.rel-borderline {
  color: var(--warning);
  background: var(--warning-soft);
  border-color: #fad8a3;
}

.rel-low,
.rel-not_relevant {
  color: var(--text-muted);
  background: var(--bg-tint);
  border-color: var(--border);
}

.prop-title {
  font-size: var(--t-md);
  font-weight: 600;
  color: var(--text);
  line-height: 1.45;
  letter-spacing: -0.005em;
}

.prop-reason {
  font-size: 13px;
  color: var(--text-soft);
  line-height: 1.6;
}

.prop-abstract summary {
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--brand);
  user-select: none;
  list-style: none;
  padding: var(--s-2) 0;
}

.prop-abstract summary::before {
  content: '+ ';
}

.prop-abstract[open] summary::before {
  content: '− ';
}

.prop-abstract p {
  margin-top: var(--s-3);
  font-size: 13px;
  color: var(--text-soft);
  line-height: 1.7;
  padding: var(--s-4);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
}

.approval-bar {
  display: flex;
  justify-content: space-between;
  gap: var(--s-3);
  padding-top: var(--s-5);
  margin-top: var(--s-2);
  border-top: 1px solid var(--border);
}

.approve-summary {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  padding: var(--s-3) var(--s-4);
  background: var(--success-soft);
  border: 1px solid #c5ecd0;
  border-radius: var(--r-sm);
  font-size: 13px;
}

.approve-summary .ok {
  font-weight: 600;
  color: var(--success);
}

.approve-summary .warn {
  color: var(--warning);
}

/* Mining diff */
.diff-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  overflow: hidden;
}

.diff-stats > div {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  text-align: center;
  padding: var(--s-7) var(--s-4);
  border-right: 1px solid var(--border);
}

.diff-stats > div:last-child {
  border-right: none;
}

.diff-stat-num {
  font-family: var(--font-mono);
  font-size: var(--t-2xl);
  font-weight: 600;
  color: var(--brand);
  line-height: 1;
  letter-spacing: -0.02em;
}

.diff-stat-lbl {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-top: var(--s-2);
}

.diff-block {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}

.diff-head {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  padding-bottom: var(--s-3);
  border-bottom: 1px solid var(--border);
}

.diff-head h4 {
  font-size: var(--t-md);
  font-weight: 600;
  color: var(--text);
}

.diff-count {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  background: var(--bg-tint);
  padding: 2px var(--s-2);
  border-radius: var(--r-sm);
}

.diff-head .prop-bulk {
  margin-left: auto;
}

.diff-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
}

.diff-chip.class-chip {
  padding: 6px var(--s-3);
  font-size: 13px;
  font-weight: 500;
  background: var(--brand);
  color: white;
  border-radius: var(--r-sm);
}

.entity-group {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}

.group-label {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--brand);
}

.group-count {
  color: var(--text-muted);
  font-weight: 500;
}

.diff-rows {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
}

.diff-row {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  padding: 8px var(--s-3) 8px var(--s-2);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  cursor: pointer;
  transition: border-color var(--speed) var(--ease), background var(--speed) var(--ease);
}

.diff-row:hover:not(.disabled) {
  border-color: var(--brand);
}

.diff-row.removed {
  background: var(--danger-soft);
  border-color: #f5c6cb;
}

.diff-row.disabled {
  cursor: default;
  opacity: 0.85;
}

.diff-row input[type='checkbox'] {
  accent-color: var(--success);
  width: 14px;
  height: 14px;
}

.diff-name {
  font-size: 13px;
  color: var(--text);
  font-weight: 500;
}

.diff-name.strike {
  text-decoration: line-through;
  color: var(--danger);
}

.triples-details summary {
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--brand);
  user-select: none;
  list-style: none;
  padding: var(--s-3) 0;
}

.triples-details summary::before {
  content: '+ ';
}

.triples-details[open] summary::before {
  content: '− ';
}

.triple-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  margin-top: var(--s-3);
}

.triple-row {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: var(--s-3);
  align-items: center;
  padding: var(--s-3) var(--s-4);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  font-size: 13px;
}

.triple-s,
.triple-o {
  color: var(--text);
  font-weight: 500;
}

.triple-p {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  color: var(--brand);
  background: var(--brand-soft);
  padding: 3px var(--s-2);
  border-radius: var(--r-sm);
  text-align: center;
}

/* Validation fixes */
.fixes {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}

.fix {
  display: grid;
  grid-template-columns: 36px 1fr auto;
  gap: var(--s-4);
  padding: var(--s-4);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  align-items: flex-start;
}

.fix-num {
  font-family: var(--font-mono);
  font-size: var(--t-sm);
  font-weight: 700;
  color: var(--brand);
}

.fix-body {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}

.fix-tag {
  align-self: flex-start;
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--brand);
  background: var(--brand-soft);
  padding: 3px var(--s-2);
  border-radius: var(--r-sm);
}

.fix-body p {
  font-size: var(--t-sm);
  color: var(--text);
  line-height: 1.6;
}

.fix-actions {
  display: flex;
  gap: var(--s-2);
}

.decided {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 6px var(--s-3);
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

/* DL-Learner */
.solutions {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}

.solution {
  display: grid;
  grid-template-columns: 36px 1fr;
  gap: var(--s-4);
  padding: var(--s-4);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
}

.rank {
  font-family: var(--font-mono);
  font-size: var(--t-sm);
  font-weight: 700;
  color: var(--brand);
}

.sol-body {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.sol-body code {
  font-family: var(--font-mono);
  font-size: 13px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  padding: var(--s-3);
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text);
}

.sol-meta {
  display: flex;
  gap: var(--s-4);
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
}

.sol-meta strong {
  color: var(--text);
  font-weight: 700;
}

.raw summary {
  cursor: pointer;
  font-size: var(--t-sm);
  color: var(--text-muted);
  font-weight: 500;
  user-select: none;
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
  max-height: 280px;
  overflow: auto;
}

.empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--s-7);
  color: var(--text-muted);
  font-size: var(--t-sm);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
}

.caption {
  font-size: 12px;
  color: var(--text-muted);
}

.good {
  color: var(--success);
  font-weight: 700;
}

.bad {
  color: var(--danger);
  font-weight: 700;
}

.ok {
  color: var(--success);
  font-weight: 700;
}

.warn-text {
  color: var(--warning);
  font-weight: 700;
}

.done-banner {
  display: flex;
  gap: var(--s-4);
  align-items: center;
  padding: var(--s-5) var(--s-6);
  background: var(--success-soft);
  border: 1px solid #c5ecd0;
  border-radius: var(--r-lg);
}

.done-icon {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: var(--success);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.done-body {
  flex: 1;
}

.done-body h4 {
  font-size: var(--t-md);
  font-weight: 600;
  color: var(--success);
}

.done-body p {
  font-size: var(--t-sm);
  color: var(--text-soft);
  margin-top: var(--s-1);
}

@media (max-width: 900px) {
  .how-steps {
    grid-template-columns: 1fr 1fr;
  }
  .cta-row {
    flex-direction: column;
    align-items: stretch;
  }
  .planned-summary {
    text-align: center;
  }
  .approval-bar {
    flex-direction: column-reverse;
  }
  .approval-bar .btn {
    width: 100%;
    justify-content: center;
  }
  .fix {
    grid-template-columns: 32px 1fr;
  }
  .fix-actions {
    grid-column: 2;
  }
  .diff-stats {
    grid-template-columns: 1fr;
  }
  .diff-stats > div {
    border-right: none;
    border-bottom: 1px solid var(--border);
  }
  .diff-stats > div:last-child {
    border-bottom: none;
  }
}
</style>
