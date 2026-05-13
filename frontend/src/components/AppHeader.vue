<script setup>
const props = defineProps({
  tabs: { type: Array, required: true },
  current: { type: String, required: true },
})

const emit = defineEmits(['select'])

function select(id) {
  if (id !== props.current) emit('select', id)
}
</script>

<template>
  <header class="header">
    <div class="left">
      <div class="logo" aria-hidden="true">
        <svg viewBox="0 0 32 32" width="28" height="28" fill="none">
          <circle cx="16" cy="16" r="14" stroke="currentColor" stroke-width="1.4" />
          <circle cx="16" cy="16" r="7" stroke="currentColor" stroke-width="1.4" />
          <circle cx="16" cy="16" r="2.5" fill="currentColor" />
        </svg>
      </div>
      <div class="title">
        <span class="name">AMD Ontology</span>
        <span class="sub">Engineering Tool</span>
      </div>
    </div>

    <nav class="tabs" aria-label="Primary">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        :class="['tab', { active: tab.id === current }]"
        :aria-current="tab.id === current ? 'page' : undefined"
        @click="select(tab.id)"
      >
        {{ tab.label }}
      </button>
    </nav>

    <div class="right">
      <span class="status-pill">
        <span class="dot" />
        <span>Backend live</span>
      </span>
    </div>
  </header>
</template>

<style scoped>
.header {
  height: var(--header-h);
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: var(--s-5);
  padding: 0 var(--s-6);
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 50;
  backdrop-filter: blur(8px);
}

.left {
  display: flex;
  align-items: center;
  gap: var(--s-3);
}

.logo {
  width: 36px;
  height: 36px;
  border-radius: var(--r-md);
  background: linear-gradient(135deg, var(--brand) 0%, var(--brand-deep) 100%);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
}

.title {
  display: flex;
  flex-direction: column;
  line-height: 1.1;
}

.name {
  font-size: var(--t-sm);
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text);
}

.sub {
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--text-muted);
  letter-spacing: 0.02em;
}

.tabs {
  display: flex;
  gap: var(--s-1);
  background: var(--bg-tint);
  padding: 4px;
  border-radius: var(--r-md);
}

.tab {
  padding: 6px var(--s-3);
  border-radius: var(--r-sm);
  font-size: var(--t-sm);
  font-weight: 500;
  color: var(--text-muted);
  transition:
    background var(--speed) var(--ease),
    color var(--speed) var(--ease),
    box-shadow var(--speed) var(--ease);
}

.tab:hover {
  color: var(--text);
}

.tab.active {
  background: var(--surface);
  color: var(--brand);
  box-shadow: var(--shadow-xs);
}

.right {
  display: flex;
  justify-content: flex-end;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  padding: 6px var(--s-3);
  background: var(--success-soft);
  border: 1px solid #c5ecd0;
  border-radius: var(--r-pill);
  font-size: 12px;
  font-weight: 500;
  color: var(--success);
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--success);
  animation: pulse 2s var(--ease) infinite;
}

@media (max-width: 720px) {
  .header {
    grid-template-columns: auto 1fr;
  }
  .right {
    display: none;
  }
  .tabs {
    overflow-x: auto;
  }
}
</style>
