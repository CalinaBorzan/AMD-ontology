<script setup>
import { ref, shallowRef, computed } from 'vue'
import AppHeader from './components/AppHeader.vue'
import LandingPage from './components/LandingPage.vue'
import ManualUpload from './components/ManualUpload.vue'
import CorpusExtraction from './components/CorpusExtraction.vue'
import OntologyGraph from './components/OntologyGraph.vue'

const tabs = [
  { id: 'landing', label: 'Landing' },
  { id: 'manual', label: 'Manual upload' },
  { id: 'corpus', label: 'Corpus extraction' },
  { id: 'graph', label: 'Graph' },
]

const components = shallowRef({
  landing: LandingPage,
  manual: ManualUpload,
  corpus: CorpusExtraction,
  graph: OntologyGraph,
})

const currentTab = ref('landing')
const activeComponent = computed(() => components.value[currentTab.value])

function setTab(id) {
  if (components.value[id]) currentTab.value = id
}
</script>

<template>
  <div class="app">
    <AppHeader :tabs="tabs" :current="currentTab" @select="setTab" />
    <main class="main">
      <component :is="activeComponent" @navigate="setTab" />
    </main>
  </div>
</template>

<style scoped>
.app {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.main {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
</style>
