<!-- frontend/src/components/OntologyEditor.vue -->
<template>
  <div class="ontology-editor">
    <div class="oe-section">
      <div class="oe-section-head">
        <h3>{{ $t('ontology.entityTypes') }} ({{ entityTypes.length }})</h3>
        <button class="oe-add" @click="addEntity">+ {{ $t('ontology.addEntity') }}</button>
      </div>
      <div v-for="(ent, ei) in entityTypes" :key="ei" class="oe-card">
        <div class="oe-row">
          <input v-model="ent.name" :placeholder="$t('ontology.typeName')" class="oe-input" />
          <button class="oe-del" @click="entityTypes.splice(ei, 1)">✕</button>
        </div>
        <input v-model="ent.description" :placeholder="$t('ontology.description')" class="oe-input" />
        <div class="oe-attrs">
          <div class="oe-attr-head">
            <span>{{ $t('ontology.attributes') }}</span>
            <button class="oe-add-sm" @click="ent.attributes.push({ name: '', type: 'text', description: '' })">+</button>
          </div>
          <div v-for="(attr, ai) in ent.attributes" :key="ai" class="oe-row">
            <input v-model="attr.name" :placeholder="$t('ontology.attrName')" class="oe-input-sm" />
            <input v-model="attr.type" :placeholder="$t('ontology.attrType')" class="oe-input-sm" />
            <input v-model="attr.description" :placeholder="$t('ontology.description')" class="oe-input-sm" />
            <button class="oe-del" @click="ent.attributes.splice(ai, 1)">✕</button>
          </div>
        </div>
      </div>
    </div>

    <div class="oe-section">
      <div class="oe-section-head">
        <h3>{{ $t('ontology.edgeTypes') }} ({{ edgeTypes.length }})</h3>
        <button class="oe-add" @click="addEdge">+ {{ $t('ontology.addEdge') }}</button>
      </div>
      <div v-for="(edge, gi) in edgeTypes" :key="gi" class="oe-card">
        <div class="oe-row">
          <input v-model="edge.name" :placeholder="$t('ontology.edgeName')" class="oe-input" />
          <button class="oe-del" @click="edgeTypes.splice(gi, 1)">✕</button>
        </div>
        <input v-model="edge.description" :placeholder="$t('ontology.description')" class="oe-input" />
        <div v-for="(st, si) in edge.source_targets" :key="si" class="oe-row">
          <select v-model="st.source" class="oe-input-sm">
            <option v-for="n in entityNames" :key="'s'+n" :value="n">{{ n }}</option>
          </select>
          <span class="oe-arrow">→</span>
          <select v-model="st.target" class="oe-input-sm">
            <option v-for="n in entityNames" :key="'t'+n" :value="n">{{ n }}</option>
          </select>
          <button class="oe-del" @click="edge.source_targets.splice(si, 1)">✕</button>
        </div>
        <button class="oe-add-sm" @click="edge.source_targets.push({ source: entityNames[0] || '', target: entityNames[0] || '' })">+ {{ $t('ontology.addPair') }}</button>
      </div>
    </div>

    <ul v-if="errors.length" class="oe-errors">
      <li v-for="(e, i) in errors" :key="i">{{ e }}</li>
    </ul>
    <ul v-if="warnings.length" class="oe-warnings">
      <li v-for="(w, i) in warnings" :key="i">{{ w }}</li>
    </ul>

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
// Deep clone so edits don't mutate the parent until saved
const entityTypes = ref(JSON.parse(JSON.stringify(props.ontology.entity_types || [])))
const edgeTypes = ref(JSON.parse(JSON.stringify(props.ontology.edge_types || [])))
const saving = ref(false)

const entityNames = computed(() => entityTypes.value.map(e => (e.name || '').trim()).filter(Boolean))

function addEntity() { entityTypes.value.push({ name: '', description: '', attributes: [], examples: [] }) }
function addEdge() { edgeTypes.value.push({ name: '', description: '', source_targets: [], attributes: [] }) }

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
        const ref = (st[role] || '').trim()
        if (ref && !names.has(ref)) errs.push(t('ontology.errUnknownRef', { name: n || '?', ref }))
      }
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

function payload() {
  return { ontology: { entity_types: entityTypes.value, edge_types: edgeTypes.value }, analysis_summary: props.analysisSummary }
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
.oe-build { background: var(--brand-primary, #FF4500); }
.oe-del { background: transparent; border: none; color: #c00; cursor: pointer; }
.oe-errors { color: #c00; font-size: 0.75rem; }
.oe-warnings { color: #b8860b; font-size: 0.75rem; }
.oe-actions { display: flex; gap: 0.6rem; }
button:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
