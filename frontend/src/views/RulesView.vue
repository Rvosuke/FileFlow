<template>
  <div class="rules">
    <div class="header">
      <h1>Rules Management</h1>
      <div class="filters">
        <label>Filter Type:</label>
        <select v-model="filterType" @change="fetchRules">
          <option value="">All</option>
          <option value="exact">Exact Match</option>
          <option value="pattern">Pattern Match</option>
          <option value="type_dir">Type/Dir Match</option>
        </select>
      </div>
    </div>

    <div v-if="loading" class="loading">Loading rules...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else-if="items.length === 0" class="empty-state">
      <p>No rules found.</p>
      <p class="hint">Add some rules using the CLI (e.g., <code>fileflow rules add-exact ...</code>) to see them here.</p>
    </div>
    <div v-else>
      <table>
        <thead>
          <tr>
            <th>Type</th>
            <th>Pattern</th>
            <th>Target Directory</th>
            <th>Confidence</th>
            <th>Created At</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in items" :key="item.id">
            <td>
              <span :class="['badge', item.match_type]">
                {{ item.match_type }}
              </span>
            </td>
            <td><code>{{ item.match_pattern }}</code></td>
            <td>{{ item.target_dir }}</td>
            <td>
              <div class="confidence-bar">
                <div class="bar" :style="{ width: (item.confidence * 100) + '%' }"></div>
                <span class="label">{{ (item.confidence * 100).toFixed(0) }}%</span>
              </div>
            </td>
            <td>{{ item.created_at ? new Date(item.created_at * 1000).toLocaleDateString() : '-' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'

const items = ref<any[]>([])
const loading = ref(true)
const error = ref('')
const filterType = ref('')

const fetchRules = async () => {
  loading.value = true
  error.value = ''
  try {
    const params: any = { limit: 100 }
    if (filterType.value) params.type = filterType.value
    const response = await axios.get('http://localhost:8000/rules', { params })
    items.value = response.data.items
  } catch (e: any) {
    error.value = 'Failed to load rules: ' + e.message
  } finally {
    loading.value = false
  }
}

onMounted(fetchRules)
</script>

<style scoped>
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
}

.badge {
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  font-size: 0.8rem;
  font-weight: bold;
}

.badge.exact { background: #e3f2fd; color: #1976d2; }
.badge.pattern { background: #f3e5f5; color: #7b1fa2; }
.badge.type_dir { background: #e8f5e9; color: #388e3c; }

code {
  background: #f5f5f5;
  padding: 0.2rem 0.4rem;
  border-radius: 4px;
}

.confidence-bar {
  width: 100px;
  height: 20px;
  background: #eee;
  border-radius: 10px;
  position: relative;
  overflow: hidden;
}

.confidence-bar .bar {
  height: 100%;
  background: #42b983;
}

.confidence-bar .label {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  text-align: center;
  font-size: 0.7rem;
  line-height: 20px;
  color: #333;
}

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
