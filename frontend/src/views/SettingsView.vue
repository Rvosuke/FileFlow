<template>
  <div class="settings">
    <h1>Configuration Settings</h1>
    <p class="description">Current read-only view of the FileFlow configuration.</p>

    <div v-if="loading" class="loading">Loading configuration...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else-if="config">
      <div v-for="(section, sectionName) in config" :key="sectionName" class="section-card">
        <h3>{{ capitalize(sectionName) }}</h3>
        <div class="config-grid">
          <div v-for="(value, key) in section" :key="key" class="config-item">
            <span class="key">{{ key }}</span>
            <span class="value">
              <code v-if="typeof value !== 'object'">{{ value }}</code>
              <ul v-else-if="Array.isArray(value)">
                <li v-for="item in value" :key="item"><code>{{ item }}</code></li>
              </ul>
              <pre v-else><code>{{ JSON.stringify(value, null, 2) }}</code></pre>
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'

const config = ref<any>(null)
const loading = ref(true)
const error = ref('')

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

onMounted(async () => {
  try {
    const response = await axios.get('http://localhost:8000/config')
    config.value = response.data
  } catch (e: any) {
    error.value = 'Failed to load configuration: ' + e.message
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.description { color: #666; margin-bottom: 2rem; }

.section-card {
  background: #fff;
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 1.5rem;
  margin-bottom: 2rem;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

h3 { margin-top: 0; color: #333; border-bottom: 1px solid #eee; padding-bottom: 0.5rem; }

.config-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1rem;
  margin-top: 1rem;
}

.config-item {
  display: flex;
  border-bottom: 1px solid #f9f9f9;
  padding: 0.5rem 0;
}

.key {
  width: 200px;
  font-weight: 600;
  color: #555;
  flex-shrink: 0;
}

.value {
  flex-grow: 1;
  word-break: break-all;
}

code {
  background: #f5f5f5;
  padding: 0.2rem 0.4rem;
  border-radius: 4px;
  font-size: 0.9rem;
}

ul { margin: 0; padding-left: 1.2rem; }
pre { margin: 0; }
</style>
