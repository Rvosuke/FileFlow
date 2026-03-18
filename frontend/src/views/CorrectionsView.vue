<template>
  <div class="corrections">
    <h1>Manual Corrections</h1>
    <p class="description">User-provided feedback that helps refine the AI's sorting rules.</p>

    <div v-if="loading" class="loading">Loading corrections...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <table>
        <thead>
          <tr>
            <th>File Path</th>
            <th>Correct Directory</th>
            <th>Status</th>
            <th>Created At</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in items" :key="item.id">
            <td class="file-path">
              <code>{{ item.file_path }}</code>
            </td>
            <td>
              <span class="dir-badge">{{ item.correct_dir }}</span>
            </td>
            <td>
              <span :class="['status-badge', item.applied ? 'applied' : 'pending']">
                {{ item.applied ? 'Applied' : 'Pending' }}
              </span>
            </td>
            <td class="date">
              {{ new Date(item.created_at * 1000).toLocaleString() }}
            </td>
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

onMounted(async () => {
  try {
    const response = await axios.get('http://localhost:8000/corrections')
    items.value = response.data.items
  } catch (e: any) {
    error.value = 'Failed to load corrections: ' + e.message
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.description { color: #666; margin-bottom: 2rem; }

code {
  background: #f5f5f5;
  padding: 0.2rem 0.4rem;
  border-radius: 4px;
  font-size: 0.85rem;
}

.dir-badge {
  background: #e1f5fe;
  color: #0288d1;
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  font-weight: 500;
}

.status-badge {
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  font-size: 0.8rem;
}
.status-badge.applied { background: #e8f5e9; color: #388e3c; }
.status-badge.pending { background: #fff3e0; color: #f57c00; }

.file-path { max-width: 400px; word-break: break-all; }
.date { white-space: nowrap; font-size: 0.9rem; color: #666; }
</style>
