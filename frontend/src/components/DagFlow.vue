<script setup lang="ts">
import { computed, reactive } from 'vue'
import { Position, VueFlow } from '@vue-flow/core'
import type { AgentNode, DagEdge } from '@/types/agentNode'

const props = defineProps<{
  nodes: AgentNode[]
  edges: DagEdge[]
}>()

const statusColor: Record<string, string> = {
  pending: '#909399',
  running: '#409eff',
  success: '#67c23a',
  failed: '#f56c6c',
  paused: '#e6a23c',
  pause_requested: '#e6a23c',
  canceled: '#f56c6c',
  cancel_requested: '#f56c6c',
  revision: '#e6a23c',
  needs_revision: '#e6a23c',
}

const centerY = 390
const manualNodePositions = reactive<Record<string, { x: number; y: number }>>({})

const nodePositions: Record<string, { x: number; y: number }> = {
  planner: { x: 0, y: centerY },
  dimension_planner: { x: 300, y: centerY },
  collector: { x: 620, y: centerY },
  evidence_extractor: { x: 1160, y: centerY },
  report_writer: { x: 2060, y: centerY },
  qa: { x: 2380, y: centerY },
  report_finalizer: { x: 2700, y: centerY },
}

const workerCounts = computed(() => ({
  collector: props.nodes.filter((node) => node.node_key.startsWith('collector_worker_')).length || 1,
  evidence: props.nodes.filter((node) => node.node_key.startsWith('evidence_worker_')).length || 1,
}))

const dimensionNodes = computed(() =>
  props.nodes.filter((node) => node.node_type === 'dimension_analyst' || node.node_key.startsWith('dimension_analysis_')),
)

function workerPosition(nodeKey: string, prefix: string, x: number, total: number) {
  const match = nodeKey.match(new RegExp(`^${prefix}_(\\d+)$`))
  if (!match) return null
  const index = Number(match[1]) - 1
  const rowGap = 120
  const startY = centerY - ((Math.max(0, total - 1) * rowGap) / 2)
  return { x, y: startY + index * rowGap }
}

function getNodePosition(node: AgentNode, index: number) {
  const manualPosition = manualNodePositions[node.node_key]
  if (manualPosition) return manualPosition

  if (node.node_type === 'dimension_analyst' || node.node_key.startsWith('dimension_analysis_')) {
    const dimensionIndex = Math.max(0, dimensionNodes.value.findIndex((item) => item.node_key === node.node_key))
    const rowGap = 126
    const total = Math.max(1, dimensionNodes.value.length)
    const startY = centerY - ((total - 1) * rowGap) / 2
    return { x: 1580, y: startY + dimensionIndex * rowGap }
  }
  return (
    nodePositions[node.node_key] ||
    workerPosition(node.node_key, 'collector_worker', 880, workerCounts.value.collector) ||
    workerPosition(node.node_key, 'evidence_worker', 1360, workerCounts.value.evidence) ||
    { x: (index % 3) * 260, y: Math.floor(index / 3) * 120 }
  )
}

function rememberNodePosition(payload: { node?: { id?: string; position?: { x: number; y: number } } }) {
  const node = payload.node
  if (!node?.id || !node.position) return
  manualNodePositions[node.id] = { x: node.position.x, y: node.position.y }
}

const flowNodes = computed(() =>
  props.nodes.map((node, index) => ({
    id: node.node_key,
    position: getNodePosition(node, index),
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    data: { label: `${node.node_name}\n${node.status}` },
    style: {
      border: node.revision_highlight
        ? '3px solid #e6a23c'
        : `2px solid ${statusColor[node.status] ?? '#c0c4cc'}`,
      borderRadius: '8px',
      width: node.node_type === 'virtual_worker' ? '160px' : node.node_type === 'dimension_analyst' ? '190px' : '210px',
      padding: node.node_type === 'virtual_worker' ? '9px' : '12px',
      whiteSpace: 'pre-line',
      fontSize: node.node_type === 'virtual_worker' ? '12px' : '13px',
      background: node.revision_highlight
        ? '#fff8e8'
        : node.node_type === 'virtual_worker' ? '#fffaf0' : node.node_type === 'dimension_analyst' ? '#f5f9ff' : '#fff',
      boxShadow: node.revision_highlight ? '0 0 0 4px rgba(230, 162, 60, 0.16)' : undefined,
    },
  })),
)

const flowEdges = computed(() =>
  props.edges.map((edge, index) => ({
    id: edge.id || `${edge.source}-${edge.target}-${edge.type || 'normal'}-${index}`,
    source: edge.source,
    target: edge.target,
    label: edge.label || undefined,
    animated: edge.type === 'revision',
    style:
      edge.type === 'revision'
        ? { stroke: '#e6a23c', strokeDasharray: '6 4', strokeWidth: 2 }
        : edge.type === 'parallel'
          ? { stroke: '#409eff', strokeDasharray: '4 4', strokeWidth: 1.5 }
        : { stroke: '#909399' },
    labelStyle:
      edge.type === 'revision'
        ? { fill: '#b88230', fontWeight: 600 }
        : edge.type === 'parallel'
          ? { fill: '#409eff', fontSize: 11 }
          : undefined,
  })),
)
</script>

<template>
  <div class="flow-shell">
    <VueFlow
      :nodes="flowNodes"
      :edges="flowEdges"
      fit-view-on-init
      @node-drag="rememberNodePosition"
      @node-drag-stop="rememberNodePosition"
    />
  </div>
</template>

<style scoped>
.flow-shell {
  height: 860px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  overflow: hidden;
  background: #fbfcfe;
}
</style>
