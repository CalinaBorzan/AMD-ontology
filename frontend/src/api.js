import axios from 'axios'

// In production (HF Spaces, etc.) the frontend is served from the same origin
// as the backend, so we use relative URLs. Locally we hit the FastAPI dev
// server explicitly on port 8000.
const isLocalDev =
  typeof window !== 'undefined' &&
  (window.location.hostname === 'localhost' ||
    window.location.hostname === '127.0.0.1') &&
  window.location.port !== '8000'

const API_URL =
  import.meta.env.VITE_API_URL ??
  (isLocalDev ? 'http://localhost:8000' : '')

export const http = axios.create({
  baseURL: API_URL,
  timeout: 60000,
})

export const api = {
  listModels: () => http.get('/api/models').then((r) => r.data),

  getOntology: () => http.get('/api/ontology').then((r) => r.data),

  extractAbstract: (payload) =>
    http.post('/api/extract/abstract', payload).then((r) => r.data),

  startRun: (payload) => http.post('/api/runs', payload).then((r) => r.data),
  listRuns: () => http.get('/api/runs').then((r) => r.data),
  getRun: (id) => http.get(`/api/runs/${id}`).then((r) => r.data),
  getRunLogs: (id, offset = 0) =>
    http.get(`/api/runs/${id}/logs`, { params: { offset } }).then((r) => r.data),
  getRunResult: (id) => http.get(`/api/runs/${id}/result`).then((r) => r.data),

  startValidation: (payload) => http.post('/api/validate', payload).then((r) => r.data),
  getFixes: (id) => http.get(`/api/validate/${id}/fixes`).then((r) => r.data),
  decideFix: (id, fixId, action) =>
    http
      .post(`/api/validate/${id}/fixes/${fixId}/decide`, { action })
      .then((r) => r.data),

  batchAdd: (payload) => http.post('/api/ontology/batch-add', payload).then((r) => r.data),
  addInstance: (payload) => http.post('/api/ontology/instances', payload).then((r) => r.data),
  addTriple: (payload) => http.post('/api/ontology/triples', payload).then((r) => r.data),
  deleteInstance: (name) =>
    http.delete(`/api/ontology/instances/${encodeURIComponent(name)}`).then((r) => r.data),
  deleteTriple: (subject, predicate, object) =>
    http.delete('/api/ontology/triples', { params: { subject, predicate, object } }).then((r) => r.data),

  fetchLiterature: (payload) =>
    http.post('/api/literature/fetch', payload).then((r) => r.data),
  getLiteratureResult: (id) =>
    http.get(`/api/literature/${id}/result`).then((r) => r.data),
  approveLiterature: (payload) =>
    http.post('/api/literature/approve', payload).then((r) => r.data),
  processLiterature: (payload) =>
    http.post('/api/literature/process', payload).then((r) => r.data),
  getRejectedLiterature: () =>
    http.get('/api/literature/rejected').then((r) => r.data),
  restoreRejectedLiterature: (pmids) =>
    http.post('/api/literature/rejected/restore', { pmids }).then((r) => r.data),
  getApprovedLiterature: () =>
    http.get('/api/literature/approved').then((r) => r.data),

  listDLExperiments: () => http.get('/api/dllearner/experiments').then((r) => r.data),
  runDLLearner: (payload) => http.post('/api/dllearner/run', payload).then((r) => r.data),
  getDLResult: (id) => http.get(`/api/dllearner/${id}/result`).then((r) => r.data),

  runHermit: () => http.post('/api/reasoner/hermit', {}).then((r) => r.data),
  getHermitResult: (id) => http.get(`/api/reasoner/hermit/${id}/result`).then((r) => r.data),
  applyInferred: (axioms) => http.post('/api/reasoner/hermit/apply-inferred', { axioms }).then((r) => r.data),

  listSnapshots: () => http.get('/api/ontology/snapshots').then((r) => r.data),
  createSnapshot: (label = '') => http.post('/api/ontology/snapshots', null, { params: { label } }).then((r) => r.data),
  restoreSnapshot: (name) => http.post('/api/ontology/snapshots/restore', { name }).then((r) => r.data),
}
