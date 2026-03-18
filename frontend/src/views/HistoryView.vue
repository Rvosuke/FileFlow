<template>
  <div class="history">
    <h1>Move History</h1>
    
    <div v-if="loading" class="loading">Loading history...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else-if="items.length === 0" class="empty-state">
      <p>No move history yet.</p>
      <p class="hint">Organized files will show up here after running <code>fileflow scan --execute</code>.</p>
    </div>
    <div v-else>
      <table>
        <thead>
          <tr>
            <th>Source Path</th>
            <th>Target Directory</th>
            <th>Applied Rule</th>
            <th>Moved At</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in items" :key="item.id">
            <td class="source">
              <code>{{ item.source_path }}</code>
            </td>
            <td class="target">{{ item.target_dir }}</td>
            <td class="rule-id">
              <span class="id-badge">#{{ item.rule_id }}</span>
            </td>
            <td class="date">
              {{ new Date(item.moved_at * 1000).toLocaleString() }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, formatApiError } from '../lib/api'

const items = ref<any[]>([])
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    const response = await api.get('/history')
    items.value = response.data.items
  } catch (e: any) {
    error.value = formatApiError(e, 'Failed to load history')
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
code {
  background: #f5f5f5;
  padding: 0.2rem 0.4rem;
  border-radius: 4px;
  font-size: 0.85rem;
}

.id-badge {
  background: #eee;
  padding: 0.2rem 0.4rem;
  border-radius: 4px;
  font-size: 0.8rem;
  font-family: monospace;
}

.source { max-width: 400px; word-break: break-all; }
.date { white-space: nowrap; font-size: 0.9rem; color: #666; }

.loading, .error, .empty-state {
  text-align: center;
  padding: 3rem;
  font-size: 1.1rem;
}

.error { color: #e74c3c; }

.empty-state {
  background: #f9f9f9;
  border-radius: 8px;
  color: #888;
  border: 1px dashed #ddd;
}

.hint { font-size: 0.9rem; margin-top: 0.5rem; }
</style>
