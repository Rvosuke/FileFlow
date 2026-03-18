<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <div class="app-container">
    <nav>
      <RouterLink to="/">Dashboard</RouterLink> |
      <RouterLink to="/rules">Rules</RouterLink> |
      <RouterLink to="/history">History</RouterLink> |
      <RouterLink to="/corrections">Corrections</RouterLink> |
      <RouterLink to="/settings">Settings</RouterLink>
    </nav>

    <main>
      <RouterView />
    </main>
  </div>
</template>

<style>
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu,
    Cantarell, 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

.app-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 1rem;
}

table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 1rem;
}

th, td {
  text-align: left;
  padding: 0.75rem;
  border-bottom: 1px solid #eee;
}

th {
  background-color: #f8f9fa;
}
</style>

<style scoped>
nav {
  padding: 1.5rem 0;
  border-bottom: 1px solid #eee;
  margin-bottom: 2rem;
}
nav a {
  margin-right: 1.5rem;
  text-decoration: none;
  color: #666;
  font-weight: 500;
}
nav a.router-link-active {
  color: #42b983;
  border-bottom: 2px solid #42b983;
  padding-bottom: 0.25rem;
}
</style>
