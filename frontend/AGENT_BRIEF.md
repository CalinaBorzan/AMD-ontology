# Frontend Agent Brief — AMD Ontology UI

## Project context

You are building the public-facing web UI for an **AMD (Age-Related Macular Degeneration) ontology engineering tool** — a bachelor's thesis project.

The backend is a Python pipeline that:
1. Reads clinical trial abstracts about AMD
2. Uses LLMs (Qwen2.5:32B / Llama-3.3-70B via Groq) with LangChain agents to extract medical entities and relations
3. Validates the extracted ontology with another LLM agent (HITL — human-in-the-loop)
4. Outputs an OWL ontology

The user is a **medical doctor / scientist**. They will use the UI to either:
- **Manual mode**: paste a single abstract and see what the LLM extracts
- **Auto mining mode**: trigger the full agentic pipeline on a corpus of abstracts

After extraction, the doctor reviews proposed fixes (HITL) and the ontology is updated.

---

## Tech stack — STRICT

Match the stack of [AlloyGraph](https://github.com/AlexLecu/AlloyGraph/tree/main/frontend) — another UTCluj project the user wants to mirror:

- **Vue 3** (Composition API only — `<script setup>`)
- **Vite** as build tool
- **axios** for HTTP
- **vis-network** for graph visualization (npm package, NOT CDN)
- **NO TypeScript** — pure JavaScript only
- **NO Pinia / Vuex** — local component state + props only
- **NO vue-router** — use conditional rendering / tabs instead (like AlloyGraph)
- **NO Tailwind / CSS-in-JS** — plain `<style scoped>` + CSS custom properties (design tokens) in `src/style.css`
- ESLint + Prettier are already configured

The Vue project is already scaffolded at `frontend/` (created with `npm create vue@latest`). Confirm by checking `frontend/package.json` exists.

---

## Pages to build (iteration 1)

For this iteration, build a working SHELL with TWO pages. Other pages will come later.

### Layout (`src/App.vue`)

Top-level structure:
```
┌──────────────────────────────────────────┐
│ HEADER: AMD Ontology Engineering Tool    │
│         [tabs: Landing | Graph]          │
├──────────────────────────────────────────┤
│                                          │
│  Active tab content                      │
│                                          │
└──────────────────────────────────────────┘
```

Use a `currentTab` ref + `<component :is="activeComponent">` for switching. No router.

### Page 1: Landing (`src/components/LandingPage.vue`)

Hero section + two action cards:

```
┌─────────────────────────────────────────┐
│  AMD Ontology Engineering Tool          │
│  Human-in-the-loop ontology curation    │
│  for Age-Related Macular Degeneration   │
└─────────────────────────────────────────┘

┌──────────────────┐    ┌──────────────────┐
│ 📚 Manual Upload │    │ 🤖 Auto Mining   │
│                  │    │                  │
│ Add a single     │    │ Run agentic LLM  │
│ abstract and see │    │ pipeline on full │
│ extracted        │    │ corpus           │
│ entities         │    │                  │
│                  │    │                  │
│ [Coming soon]    │    │ [Coming soon]    │
└──────────────────┘    └──────────────────┘
```

Cards are visually clickable but for now show "Coming soon" — these pages will come in iteration 2.

### Page 2: Ontology Graph (`src/components/OntologyGraph.vue`)

A `vis-network` graph displaying the ontology. For iteration 1, **load static mock data from `public/mock_ontology.json`** (see schema below). In iteration 2 we'll wire it to the real backend.

Layout:
```
┌────────────┬─────────────────────────────┐
│  SIDEBAR   │  GRAPH (vis-network)         │
│            │                              │
│  Filters:  │  [interactive node-edge      │
│  [ ] Show  │   visualization]             │
│  classes   │                              │
│  [ ] Show  │                              │
│  instances │                              │
│  [ ] Show  │                              │
│  triples   │                              │
│            │                              │
│  Search:   │                              │
│  [____]    │                              │
└────────────┴─────────────────────────────┘
```

Mock data format (`public/mock_ontology.json`):
```json
{
  "classes": {
    "Disease": { "subclasses": ["AMD"], "instances": ["Glaucoma", "Cataract"] },
    "Treatment": { "subclasses": [], "instances": ["Ranibizumab", "Aflibercept"] },
    "Biomarker": { "subclasses": [], "instances": ["CFH", "ARMS2", "HTRA1"] }
  },
  "properties": {
    "treats": { "examples": [["Ranibizumab", "treats", "AMD"]] },
    "associatedWith": { "examples": [["CFH", "associatedWith", "AMD"]] }
  }
}
```

Map this to vis-network nodes/edges:
- Each class → node with `group: "class"` (color e.g. blue)
- Each instance → node with `group: "instance"` (color e.g. green) connected to its parent class with edge `rdf:type`
- Each triple → edge between subject and object with the predicate as label

Use vis-network's hierarchical or barnesHut physics layout — pick what looks readable.

---

## Design system (`src/style.css`)

Define CSS custom properties for the design tokens. Match AlloyGraph's approach:

```css
:root {
  /* Spacing */
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;

  /* Typography */
  --font-size-sm: 14px;
  --font-size-md: 16px;
  --font-size-lg: 20px;
  --font-size-xl: 28px;
  --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;

  /* Colors — clean, professional, slight medical feel */
  --color-bg: #f7f8fa;
  --color-bg-card: #ffffff;
  --color-text: #1a202c;
  --color-text-muted: #718096;
  --color-primary: #2b6cb0;       /* deep blue, medical */
  --color-primary-hover: #2c5282;
  --color-border: #e2e8f0;
  --color-success: #38a169;
  --color-warning: #d69e2e;
  --color-danger: #e53e3e;

  /* Shadows */
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
  --shadow-md: 0 4px 6px rgba(0,0,0,0.07);
  --shadow-lg: 0 10px 15px rgba(0,0,0,0.1);

  /* Transitions */
  --transition-base: 150ms ease;

  /* Border radius */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: var(--font-family);
  background: var(--color-bg);
  color: var(--color-text);
  font-size: var(--font-size-md);
}
```

All component styles use these tokens — never hardcoded values like `#fff` or `12px`.

---

## File structure to produce

```
frontend/
├── src/
│   ├── App.vue                    # tab shell with header
│   ├── main.js                    # mount + import './style.css'
│   ├── style.css                  # design tokens (above)
│   ├── components/
│   │   ├── AppHeader.vue          # title + tab nav
│   │   ├── LandingPage.vue        # hero + 2 action cards
│   │   └── OntologyGraph.vue      # vis-network + sidebar filters
│   └── api.js                     # axios wrapper (placeholder for now)
└── public/
    └── mock_ontology.json         # static AMD ontology snapshot
```

---

## Implementation requirements

1. **No premature abstractions** — if a piece of state is used in one component, keep it local. Don't introduce stores or composables until needed.
2. **Components must be self-contained** — each `.vue` file has its own `<style scoped>` block. No global classes leak across components.
3. **vis-network setup** — install with `npm install vis-network` and import as `import { Network } from 'vis-network/standalone'`.
4. **Responsive enough** — works on a 1280px+ desktop. Mobile is not a priority.
5. **Loading states** — when `mock_ontology.json` is being fetched, show a simple "Loading..." text.
6. **Error states** — if fetch fails, show a small red error message. No fancy modals.
7. **No console.log litter** in committed code.
8. **Comments**: only when WHY is non-obvious. Don't comment WHAT the code does.
9. **`api.js`** — add a single placeholder export, e.g.
   ```js
   import axios from 'axios'
   const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
   export const api = axios.create({ baseURL: API_URL })
   ```

---

## Out of scope for iteration 1

Do NOT build these yet:
- ❌ Manual upload page (iteration 2)
- ❌ Auto mining page (iteration 2)
- ❌ HITL review queue (iteration 2)
- ❌ Real backend wiring (iteration 2)
- ❌ Dark mode
- ❌ Authentication
- ❌ Onboarding tour (driver.js)
- ❌ Internationalization
- ❌ Tests

Just the **shell + landing + graph viewer with mock data**.

---

## Acceptance criteria

When done, running `npm run dev` from `frontend/` should:
1. Start Vite at `http://localhost:5173`
2. Show the AMD Ontology header with two tabs ("Landing" and "Graph")
3. Landing tab shows hero + two cards
4. Graph tab loads `mock_ontology.json` and renders an interactive vis-network graph
5. Clicking a node in the graph should at least log the node id to console (full details panel comes later)
6. No console errors on load
7. Run `npm run lint` cleanly (no errors; warnings are OK)

---

## Reference (AlloyGraph style cues)

Browse `https://github.com/AlexLecu/AlloyGraph/tree/main/frontend/src` and match:
- Plain `.vue` SFC structure with `<script setup>`
- Scoped CSS with custom properties
- Simple component composition without state mgmt libraries
- Card-based UI with subtle shadows

Don't copy code verbatim — just match the **style and structure**.

---

## Questions to ask BEFORE starting

If anything in this brief is ambiguous, ask the user. Specifically:
- Confirm `frontend/` already has Vue scaffolded (check `package.json`)?
- Is there a real ontology JSON file to use instead of mock? (look at `results/amd/final/amd_ontology_final.json`)
- Should the graph use horizontal or vertical layout by default?

Otherwise, start coding. Iterate until acceptance criteria pass.
