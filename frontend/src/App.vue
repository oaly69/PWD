<template>
  <router-view />
  <div class="toasts">
    <div v-for="t in state.toasts" :key="t.id" class="toast" :class="t.type">{{ t.message }}</div>
  </div>
</template>

<script setup>
import { state } from './api'
</script>
