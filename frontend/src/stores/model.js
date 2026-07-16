import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/api'

export const useModelStore = defineStore('model', () => {
  const models = ref([])
  const currentModel = ref(null)
  const currentModelId = ref('')
  const loading = ref(false)
  const eventActions = ref([])

  const modelMap = computed(() => {
    const m = {}
    models.value.forEach(mod => { m[mod.model_id] = mod })
    return m
  })

  function getModelById(modelId) {
    return modelMap.value[modelId] || null
  }

  function resolveModelId(machineModel) {
    if (!machineModel) return 'GENERIC-ETCH'
    if (modelMap.value[machineModel]) return machineModel
    const upper = machineModel.toUpperCase().replace(/\s+/g, '-')
    if (modelMap.value[upper]) return upper
    for (const id of Object.keys(modelMap.value)) {
      const idNorm = id.toUpperCase().replace(/[-_\s]/g, '')
      const modelNorm = machineModel.toUpperCase().replace(/[-_\s]/g, '')
      if (idNorm === modelNorm || idNorm.includes(modelNorm) || modelNorm.includes(idNorm)) {
        return id
      }
    }
    return 'GENERIC-ETCH'
  }

  function getViewMode(machineModel) {
    const modelId = resolveModelId(machineModel)
    const m = modelMap.value[modelId]
    return m ? m.view_mode : 'threejs'
  }

  async function loadModels() {
    if (loading.value) return
    loading.value = true
    try {
      const data = await api.getModels()
      models.value = data || []
      preloadModelAssets(data || [])
    } catch (e) {
      console.error('[modelStore] 加载机台型号失败:', e)
    } finally {
      loading.value = false
    }
  }

  function preloadModelAssets(modelList) {
    const urls = new Set()
    modelList.forEach(m => {
      let cfg = m.views_config
      if (typeof cfg === 'string') {
        try { cfg = JSON.parse(cfg) } catch (e) { cfg = null }
      }
      const src = cfg?.view_3d?.model_source || cfg?.view_3d?.model_url
      if (src && !src.startsWith('http')) urls.add(src)
    })
    urls.forEach(url => {
      fetch(url).catch(e => console.warn('[modelStore] 预加载模型资源失败:', url, e))
    })
  }

  async function loadModelDetail(modelId) {
    try {
      const data = await api.getModel(modelId)
      currentModel.value = data
      currentModelId.value = modelId
      eventActions.value = data.event_action_mappings || []
      const idx = models.value.findIndex(m => m.model_id === modelId)
      if (idx >= 0) models.value[idx] = data
      return data
    } catch (e) {
      console.error('[modelStore] 加载型号详情失败:', e)
      return null
    }
  }

  async function createModel(payload) {
    const data = await api.createModel(payload)
    models.value.push(data)
    return data
  }

  async function updateModel(modelId, payload) {
    const data = await api.updateModel(modelId, payload)
    const idx = models.value.findIndex(m => m.model_id === modelId)
    if (idx >= 0) models.value[idx] = data
    if (currentModelId.value === modelId) currentModel.value = data
    return data
  }

  async function deleteModel(modelId) {
    await api.deleteModel(modelId)
    models.value = models.value.filter(m => m.model_id !== modelId)
    if (currentModelId.value === modelId) {
      currentModel.value = null
      currentModelId.value = ''
    }
  }

  async function duplicateModel(modelId, payload) {
    const data = await api.duplicateModel(modelId, payload)
    models.value.push(data)
    return data
  }

  return {
    models,
    currentModel,
    currentModelId,
    loading,
    eventActions,
    modelMap,
    getModelById,
    resolveModelId,
    getViewMode,
    loadModels,
    loadModelDetail,
    createModel,
    updateModel,
    deleteModel,
    duplicateModel,
  }
})
