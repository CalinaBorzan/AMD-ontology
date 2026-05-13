<script setup>
import { onMounted, ref, watch } from 'vue'
import { api } from '../api.js'

const props = defineProps({
  modelValue: { type: Object, default: null },
  label: { type: String, default: 'Model' },
})

const emit = defineEmits(['update:modelValue'])

const models = ref([])
const status = ref('loading')
const errorMessage = ref('')
const selectedId = ref(props.modelValue?.id || '')

watch(
  () => props.modelValue,
  (v) => {
    if (v?.id && v.id !== selectedId.value) selectedId.value = v.id
  },
)

function pick(id) {
  selectedId.value = id
  const m = models.value.find((x) => x.id === id)
  if (m) emit('update:modelValue', { id: m.id, provider: m.provider })
}

onMounted(async () => {
  try {
    const data = await api.listModels()
    models.value = data
    if (!selectedId.value && data.length) pick(data[0].id)
    status.value = 'ready'
  } catch (err) {
    errorMessage.value = err.message || 'Failed to load models'
    status.value = 'error'
  }
})
</script>

<template>
  <div class="field">
    <label class="lbl" :for="`model-${label}`">{{ label }}</label>
    <div class="select-wrap">
      <select
        :id="`model-${label}`"
        :value="selectedId"
        :disabled="status !== 'ready'"
        @change="pick($event.target.value)"
      >
        <option v-if="status === 'loading'" value="">Loading…</option>
        <option v-else-if="status === 'error'" value="">{{ errorMessage }}</option>
        <option v-for="m in models" :key="m.id" :value="m.id">
          {{ m.name }} · {{ m.provider }}
        </option>
      </select>
      <span class="chev" aria-hidden="true">
        <svg viewBox="0 0 12 12" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M3 4.5l3 3 3-3" />
        </svg>
      </span>
    </div>
    <p v-if="selectedId" class="caption">
      {{ models.find((m) => m.id === selectedId)?.description }}
    </p>
  </div>
</template>

<style scoped>
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

.select-wrap {
  position: relative;
}

select {
  appearance: none;
  -webkit-appearance: none;
  width: 100%;
  padding: var(--s-3) var(--s-6) var(--s-3) var(--s-3);
  font-family: var(--font);
  font-size: var(--t-sm);
  color: var(--text);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  outline: none;
  cursor: pointer;
  transition: border-color var(--speed) var(--ease), box-shadow var(--speed) var(--ease);
}

select:hover:not(:disabled) {
  border-color: var(--border-strong);
}

select:focus {
  border-color: var(--border-focus);
  box-shadow: var(--shadow-focus);
}

select:disabled {
  background: var(--bg-tint);
  color: var(--text-muted);
  cursor: not-allowed;
}

.chev {
  position: absolute;
  right: var(--s-3);
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-muted);
  pointer-events: none;
  display: flex;
}

.caption {
  font-size: 12px;
  color: var(--text-muted);
}
</style>
