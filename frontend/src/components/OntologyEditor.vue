<!-- frontend/src/components/OntologyEditor.vue -->
<template>
  <div class="ontology-editor">
    <div class="oe-section">
      <div class="oe-section-head">
        <h3>{{ $t('ontology.entityTypes') }} ({{ entityTypes.length }})</h3>
        <button class="oe-add" @click="addEntity">+ {{ $t('ontology.addEntity') }}</button>
      </div>
      <div v-for="ent in entityTypes" :key="ent._uid" class="oe-card">
        <div class="oe-row">
          <input v-model="ent.name" :placeholder="$t('ontology.typeName')" class="oe-input" />
          <button class="oe-del" @click="removeByUid(entityTypes, ent._uid)">✕</button>
        </div>
        <input v-model="ent.description" :placeholder="$t('ontology.description')" class="oe-input" />
        <div class="oe-attrs">
          <div class="oe-attr-head">
            <span>{{ $t('ontology.attributes') }}</span>
            <button class="oe-add-sm" @click="ent.attributes.push(newAttr())">+</button>
          </div>
          <div v-for="attr in ent.attributes" :key="attr._uid" class="oe-row">
            <input v-model="attr.name" :placeholder="$t('ontology.attrName')" class="oe-input-sm" />
            <input v-model="attr.type" :placeholder="$t('ontology.attrType')" class="oe-input-sm" />
            <input v-model="attr.description" :placeholder="$t('ontology.description')" class="oe-input-sm" />
            <button class="oe-del" @click="removeByUid(ent.attributes, attr._uid)">✕</button>
          </div>
        </div>
      </div>
    </div>

    <div class="oe-section">
      <div class="oe-section-head">
        <h3>{{ $t('ontology.edgeTypes') }} ({{ edgeTypes.length }})</h3>
        <button class="oe-add" @click="addEdge">+ {{ $t('ontology.addEdge') }}</button>
      </div>
      <div v-for="edge in edgeTypes" :key="edge._uid" class="oe-card">
        <div class="oe-row">
          <input v-model="edge.name" :placeholder="$t('ontology.edgeName')" class="oe-input" />
          <button class="oe-del" @click="removeByUid(edgeTypes, edge._uid)">✕</button>
        </div>
        <input v-model="edge.description" :placeholder="$t('ontology.description')" class="oe-input" />
        <div v-for="st in edge.source_targets" :key="st._uid" class="oe-row">
          <select v-model="st.source" class="oe-input-sm">
            <option v-for="n in entityNames" :key="'s'+n" :value="n">{{ n }}</option>
          </select>
          <span class="oe-arrow">→</span>
          <select v-model="st.target" class="oe-input-sm">
            <option v-for="n in entityNames" :key="'t'+n" :value="n">{{ n }}</option>
          </select>
          <button class="oe-del" @click="removeByUid(edge.source_targets, st._uid)">✕</button>
        </div>
        <button class="oe-add-sm" @click="edge.source_targets.push(newSourceTarget())">+ {{ $t('ontology.addPair') }}</button>
        <div class="oe-attrs">
          <div class="oe-attr-head">
            <span>{{ $t('ontology.attributes') }}</span>
            <button class="oe-add-sm" @click="edge.attributes.push(newAttr())">+</button>
          </div>
          <div v-for="attr in edge.attributes" :key="attr._uid" class="oe-row">
            <input v-model="attr.name" :placeholder="$t('ontology.attrName')" class="oe-input-sm" />
            <input v-model="attr.type" :placeholder="$t('ontology.attrType')" class="oe-input-sm" />
            <input v-model="attr.description" :placeholder="$t('ontology.description')" class="oe-input-sm" />
            <button class="oe-del" @click="removeByUid(edge.attributes, attr._uid)">✕</button>
          </div>
        </div>
      </div>
    </div>

    <ul v-if="errors.length" class="oe-errors">
      <li v-for="(e, i) in errors" :key="i">{{ e }}</li>
    </ul>
    <ul v-if="warnings.length" class="oe-warnings">
      <li v-for="(w, i) in warnings" :key="i">{{ w }}</li>
    </ul>

    <div class="oe-section">
      <label class="oe-label">{{ $t('ontology.analysisSummary') }}</label>
      <textarea v-model="analysisSummary" class="oe-textarea" rows="4" />
    </div>

    <div class="oe-actions">
      <button class="oe-save" :disabled="saving || errors.length > 0" @click="onSave">
        {{ saving ? $t('common.loading') : $t('ontology.save') }}
      </button>
      <button class="oe-build" :disabled="saving || errors.length > 0" @click="onApproveBuild">
        {{ $t('ontology.approveBuild') }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { saveOntology } from '@/api/graph'

const props = defineProps({
  projectId: { type: String, required: true },
  ontology: { type: Object, required: true },
  analysisSummary: { type: String, default: '' },
})
const emit = defineEmits(['saved', 'approve-build'])
const { t } = useI18n()

const RESERVED = ['name', 'uuid', 'group_id', 'created_at', 'summary']

// Stable uid counter — survives JSON.parse/stringify round-trips
let _uidCounter = 0
const nextUid = () => ++_uidCounter

function assignUids(obj) {
  obj._uid = nextUid()
  return obj
}

function newAttr() {
  return assignUids({ name: '', type: 'text', description: '' })
}

function newSourceTarget() {
  return assignUids({ source: entityNames.value[0] || '', target: entityNames.value[0] || '' })
}

function removeByUid(arr, uid) {
  const idx = arr.findIndex(o => o._uid === uid)
  if (idx !== -1) arr.splice(idx, 1)
}

// Deep clone incoming ontology and stamp every nested object with a _uid
function cloneWithUids(ontology) {
  const raw = JSON.parse(JSON.stringify(ontology))
  const entityTypes = (raw.entity_types || []).map(ent => {
    ent._uid = nextUid()
    ent.attributes = (ent.attributes || []).map(a => { a._uid = nextUid(); return a })
    ent.examples = ent.examples || []
    return ent
  })
  const edgeTypes = (raw.edge_types || []).map(edge => {
    edge._uid = nextUid()
    edge.source_targets = (edge.source_targets || []).map(st => { st._uid = nextUid(); return st })
    edge.attributes = (edge.attributes || []).map(a => { a._uid = nextUid(); return a })
    return edge
  })
  return { entityTypes, edgeTypes }
}

const { entityTypes, edgeTypes } = (() => {
  const cloned = cloneWithUids(props.ontology)
  return { entityTypes: ref(cloned.entityTypes), edgeTypes: ref(cloned.edgeTypes) }
})()

// FIX 2: editable analysis summary
const analysisSummary = ref(props.analysisSummary || '')

const saving = ref(false)

const entityNames = computed(() => entityTypes.value.map(e => (e.name || '').trim()).filter(Boolean))

function addEntity() {
  entityTypes.value.push(assignUids({ name: '', description: '', attributes: [], examples: [] }))
}
function addEdge() {
  edgeTypes.value.push(assignUids({ name: '', description: '', source_targets: [], attributes: [] }))
}

const errors = computed(() => {
  const errs = []
  const seenE = new Set()
  for (const ent of entityTypes.value) {
    const n = (ent.name || '').trim()
    if (!n) { errs.push(t('ontology.errEmptyEntity')); continue }
    if (seenE.has(n)) errs.push(t('ontology.errDupEntity', { name: n }))
    seenE.add(n)
    const seenA = new Set()
    for (const a of ent.attributes || []) {
      const an = (a.name || '').trim()
      if (!an) { errs.push(t('ontology.errEmptyAttr', { type: n })); continue }
      if (RESERVED.includes(an)) errs.push(t('ontology.errReservedAttr', { attr: an, type: n }))
      if (seenA.has(an)) errs.push(t('ontology.errDupAttr', { attr: an, type: n }))
      seenA.add(an)
    }
  }
  const names = new Set(entityNames.value)
  const seenG = new Set()
  for (const g of edgeTypes.value) {
    const n = (g.name || '').trim()
    if (!n) errs.push(t('ontology.errEmptyEdge'))
    else { if (seenG.has(n)) errs.push(t('ontology.errDupEdge', { name: n })); seenG.add(n) }
    for (const st of g.source_targets || []) {
      for (const role of ['source', 'target']) {
        // FIX 4: renamed from `ref` to `refName` to avoid shadowing Vue's ref
        const refName = (st[role] || '').trim()
        if (refName && !names.has(refName)) errs.push(t('ontology.errUnknownRef', { name: n || '?', ref: refName }))
      }
    }
    // FIX 1: validate edge attributes exactly like entity attributes
    const seenA = new Set()
    for (const a of g.attributes || []) {
      const an = (a.name || '').trim()
      if (!an) { errs.push(t('ontology.errEmptyAttr', { type: n || '?' })); continue }
      if (RESERVED.includes(an)) errs.push(t('ontology.errReservedAttr', { attr: an, type: n || '?' }))
      if (seenA.has(an)) errs.push(t('ontology.errDupAttr', { attr: an, type: n || '?' }))
      seenA.add(an)
    }
  }
  return errs
})

const warnings = computed(() => {
  const w = []
  if (entityTypes.value.length !== 10) w.push(t('ontology.warnEntityCount', { n: entityTypes.value.length }))
  if (edgeTypes.value.length < 6 || edgeTypes.value.length > 10) w.push(t('ontology.warnEdgeCount', { n: edgeTypes.value.length }))
  for (const fb of ['Person', 'Organization']) if (!entityNames.value.includes(fb)) w.push(t('ontology.warnFallback', { fb }))
  return w
})

// Strip _uid from every object before sending to backend
function stripUids(obj) {
  if (Array.isArray(obj)) return obj.map(stripUids)
  if (obj && typeof obj === 'object') {
    const out = {}
    for (const [k, v] of Object.entries(obj)) {
      if (k === '_uid') continue
      out[k] = stripUids(v)
    }
    return out
  }
  return obj
}

function payload() {
  return {
    ontology: {
      entity_types: stripUids(entityTypes.value),
      edge_types: stripUids(edgeTypes.value),
    },
    // FIX 2: send editable summary instead of prop
    analysis_summary: analysisSummary.value,
  }
}

async function onSave() {
  if (errors.value.length) return
  saving.value = true
  try { const res = await saveOntology(props.projectId, payload()); emit('saved', res.data) }
  finally { saving.value = false }
}

async function onApproveBuild() {
  if (errors.value.length) return
  saving.value = true
  try { const res = await saveOntology(props.projectId, payload()); emit('saved', res.data); emit('approve-build') }
  finally { saving.value = false }
}
</script>

<style scoped>
.ontology-editor { display: flex; flex-direction: column; gap: 1rem; font-family: 'JetBrains Mono', monospace; }
.oe-section-head { display: flex; justify-content: space-between; align-items: center; }
.oe-card { border: 1px solid #EAEAEA; padding: 0.6rem; margin: 0.4rem 0; display: flex; flex-direction: column; gap: 0.4rem; }
.oe-row { display: flex; gap: 0.4rem; align-items: center; }
.oe-input, .oe-input-sm { border: 1px solid #CCC; padding: 4px 8px; font-size: 0.8rem; flex: 1; }
.oe-input-sm { font-size: 0.75rem; }
.oe-arrow { color: #999; }
.oe-add, .oe-add-sm, .oe-save, .oe-build { font-family: 'JetBrains Mono', monospace; cursor: pointer; border: 1px solid #CCC; background: transparent; padding: 4px 10px; font-size: 0.8rem; }
.oe-save, .oe-build { background: #000; color: #fff; border: none; padding: 8px 18px; }
.oe-build { background: var(--brand-primary, #5BAEDC); }
.oe-del { background: transparent; border: none; color: #c00; cursor: pointer; }
.oe-errors { color: #c00; font-size: 0.75rem; }
.oe-warnings { color: #b8860b; font-size: 0.75rem; }
.oe-actions { display: flex; gap: 0.6rem; }
.oe-label { font-size: 0.8rem; font-weight: bold; margin-bottom: 0.25rem; display: block; }
.oe-textarea { width: 100%; border: 1px solid #CCC; padding: 6px 8px; font-size: 0.8rem; font-family: 'JetBrains Mono', monospace; resize: vertical; box-sizing: border-box; }
button:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
