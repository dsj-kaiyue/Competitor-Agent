<script setup lang="ts">
import { computed } from 'vue'
import { VueFlow } from '@vue-flow/core'
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
  revision: '#e6a23c',
  needs_revision: '#e6a23c',
}

const nodePositions: Record<string, { x: number; y: number }> = {
  planner: { x: 0, y: 260 },
  collector: { x: 230, y: 260 },
  evidence_extractor: { x: 620, y: 260 },
  feature_analysis: { x: 1040, y: 40 },
  pricing_analysis: { x: 1040, y: 180 },
  market_analysis: { x: 1040, y: 320 },
  security_analysis: { x: 1040, y: 460 },
  report_writer: { x: 1340, y: 260 },
  qa: { x: 1600, y: 260 },
}

const workerCounts = computed(() => ({
  collector: props.nodes.filter((node) => node.node_key.startsWith('collector_worker_')).length || 1,
  evidence: props.nodes.filter((node) => node.node_key.startsWith('evidence_worker_')).length || 1,
}))

function workerPosition(nodeKey: string, prefix: string, x: number, total: number) {
  const match = nodeKey.match(new RegExp(`^${prefix}_(\\d+)$`))
  if (!match) return null
  const index = Number(match[1]) - 1
  const rowGap = 88
  const startY = 260 - ((Math.max(0, total - 1) * rowGap) / 2)
  return { x, y: startY + index * rowGap }
}

function getNodePosition(node: AgentNode, index: number) {
  return (
    nodePositions[node.node_key] ||
    workerPosition(node.node_key, 'collector_worker', 430, workerCounts.value.collector) ||
    workerPosition(node.node_key, 'evidence_worker', 820, workerCounts.value.evidence) ||
    { x: (index % 3) * 260, y: Math.floor(index / 3) * 120 }
  )
}

const flowNodes = computed(() =>
  props.nodes.map((node, index) => ({
    id: node.node_key,
    position: getNodePosition(node, index),
    data: { label: `${node.node_name}\n${node.status}` },
    style: {
      border: `2px solid ${statusColor[node.status] ?? '#c0c4cc'}`,
      borderRadius: '8px',
      width: node.node_type === 'virtual_worker' ? '160px' : '210px',
      padding: node.node_type === 'virtual_worker' ? '9px' : '12px',
      whiteSpace: 'pre-line',
      fontSize: node.node_type === 'virtual_worker' ? '12px' : '13px',
      background: node.node_type === 'virtual_worker' ? '#fffaf0' : '#fff',
    },
  })),
)

const flowEdges = computed(() =>
  props.edges.map((edge) => ({
    id: `${edge.source}-${edge.target}-${edge.type || 'normal'}`,
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
    <VueFlow :nodes="flowNodes" :edges="flowEdges" fit-view-on-init />
  </div>
</template>

<style scoped>
.flow-shell {
  height: 680px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  overflow: hidden;
  background: #fbfcfe;
}
</style>
