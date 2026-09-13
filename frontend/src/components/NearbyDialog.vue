<template>
  <el-dialog v-model="visible" title="查找附近对象" width="460px">
    <div class="nearby-body" v-if="target">
      <div class="nb-from"><b>{{ target.name }}</b>（{{ target.feature_type }}）</div>
      <el-radio-group v-model="radius" class="nb-radius">
        <el-radio-button :value="100">100m</el-radio-button>
        <el-radio-button :value="500">500m</el-radio-button>
        <el-radio-button :value="1000">1km</el-radio-button>
        <el-radio-button :value="2000">2km</el-radio-button>
      </el-radio-group>
      <el-button type="primary" size="small" :loading="loading" @click="run" class="nb-btn">
        查询
      </el-button>

      <div v-if="results.length" class="nearby-results">
        <div v-for="r in results" :key="r.feature_id" class="nb-item">
          <span>{{ r.name }}</span>
          <span class="dist">{{ Math.round(r.distance_m) }}m</span>
        </div>
      </div>
      <el-empty v-else-if="queried" description="范围内没有对象" :image-size="60" />
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { featureApi } from '@/api'
import type { Feature, NearbyResult } from '@/types'

const props = defineProps<{ projectId: string }>()
const visible = ref(false)
const target = ref<Feature | null>(null)
const radius = ref(500)
const loading = ref(false)
const results = ref<NearbyResult[]>([])
const queried = ref(false)

function open(f: Feature) {
  target.value = f
  radius.value = 500
  results.value = []
  queried.value = false
  visible.value = true
  run()
}

async function run() {
  const f = target.value
  if (!f) return
  const g = f.geometry_display as any
  let lng = 0
  let lat = 0
  if (f.feature_type === 'point') {
    ;[lng, lat] = g.coordinates
  } else if (f.feature_type === 'circle') {
    ;[lng, lat] = g.center
  } else {
    return
  }
  loading.value = true
  try {
    const data = await featureApi.nearby(props.projectId, lng, lat, radius.value)
    results.value = data.items
  } finally {
    loading.value = false
    queried.value = true
  }
}

defineExpose({ open })
</script>

<style scoped>
.nb-head { font-size: 14px; margin-bottom: 12px; }
.radius { margin-right: 12px; }
.nb-btn { margin-top: 12px; }
.nearby-results { margin-top: 12px; max-height: 220px; overflow: auto; border-top: 1px solid #f0f0f0; }
.nb-item { display: flex; justify-content: space-between; padding: 6px 2px; font-size: 13px; border-bottom: 1px solid #f7f7f7; }
.dist { color: #1677ff; }
</style>