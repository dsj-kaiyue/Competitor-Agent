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
}

const flowNodes = computed(() =>
  props.nodes.map((node, index) => ({
    id: node.node_key,
    position: { x: (index % 3) * 260, y: Math.floor(index / 3) * 120 },
    data: { label: `${node.node_name}\n${node.status}` },
    style: {
      border: `2px solid ${statusColor[node.status] ?? '#c0c4cc'}`,
      borderRadius: '8px',
      width: '210px',
      padding: '12px',
      whiteSpace: 'pre-line',
      fontSize: '13px',
    },
  })),
)

const flowEdges = computed(() =>
  props.edges.map((edge) => ({
    id: `${edge.source}-${edge.target}`,
    source: edge.source,
    target: edge.target,
    animated: true,
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
  height: 420px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  overflow: hidden;
  background: #fbfcfe;
}
</style>
