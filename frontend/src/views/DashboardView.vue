<template>
  <div class="dashboard">
    <h1>FileFlow Dashboard</h1>
    <div v-if="loading" class="loading">Loading dashboard data...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else-if="status" class="status-grid">
      <div class="card">
        <h3>System Paths</h3>
        <p><strong>Home:</strong> {{ status.home }}</p>
        <p><strong>Config:</strong> {{ status.config_file }}</p>
        <p><strong>Database:</strong> {{ status.database_file }}</p>
      </div>
      
      <div class="card">
        <h3>Statistics</h3>
        <div class="stats">
          <div class="stat-item">
            <span class="label">Move Records</span>
            <span class="value">{{ status.stats.move_records }}</span>
          </div>
          <div class="stat-item">
            <span class="label">Rule Cache</span>
            <span class="value">{{ status.stats.rule_cache_rows }}</span>
          </div>
          <div class="stat-item">
            <span class="label">Manual Corrections</span>
            <span class="value">{{ status.stats.corrections }}</span>
          </div>
          <div class="stat-item">
            <span class="label">Total Scans</span>
            <span class="value">{{ status.stats.scan_logs }}</span>
          </div>
        </div>
        <p v-if="status.stats.last_scan_at" class="last-scan">
          Last scan: {{ new Date(status.stats.last_scan_at * 1000).toLocaleString() }}
        </p>
      </div>

      <div class="card full-width">
        <h3>Monitored Sources</h3>
        <ul>
          <li v-for="source in status.sources" :key="source">{{ source }}</li>
        </ul>
        <p><strong>Target Root:</strong> {{ status.target_root }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, formatApiError } from '../lib/api'

const status = ref<any>(null)
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    const response = await api.get('/status')
    status.value = response.data
  } catch (e: any) {
    console.error(e)
    error.value = formatApiError(e, 'Failed to load status. Make sure the API server is running')
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 1.5rem;
  margin-top: 1rem;
}

.card {
  background: #fff;
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 1.5rem;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

.full-width {
  grid-column: 1 / -1;
}

.stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin: 1rem 0;
}

.stat-item {
  display: flex;
  flex-direction: column;
}

.label {
  font-size: 0.85rem;
  color: #666;
}

.value {
  font-size: 1.5rem;
  font-weight: bold;
  color: #42b983;
}

.last-scan {
  font-size: 0.85rem;
  color: #888;
  margin-top: 1rem;
}

.loading, .error {
  text-align: center;
  padding: 2rem;
  font-size: 1.2rem;
}

.error {
  color: #e74c3c;
}
</style>
