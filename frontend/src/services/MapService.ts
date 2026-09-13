/**
 * 地图抽象层：封装高德 AMap JS API 2.0。
 * 所有业务代码只与 MapService 交互，不直接调用 window.AMap.xxx。
 * 未来若更换 MapLibre，只需新增实现并切换工厂。
 */
import type { Feature } from '@/types'

export type MapToolType = 'select' | 'point' | 'circle' | 'polyline' | 'polygon' | 'measure' | 'area'
export type MapBaseType = 'normal' | 'satellite'

export interface MapServiceOptions {
  container: HTMLElement
  amapKey: string
  securityCode?: string
  center?: [number, number]
  zoom?: number
  /** WebGL 上下文丢失时回调（如 GPU 崩溃/显存不足），由上层销毁并重建地图 */
  onContextLost?: () => void
}

export interface MapService {
  init(): Promise<void>
  destroy(): void
  map: any

  // Overlay 管理
  setFeatures(features: Feature[]): void
  upsertFeature(feature: Feature): void
  removeFeature(featureId: string): void
  clearAll(): void
  fitView(ids?: string[]): void
  setFeatureVisibility(featureId: string, visible: boolean): void

  // 交互
  setTool(tool: MapToolType, onResult?: (geometry: unknown, tool: MapToolType) => void): void
  onFeatureClick(cb: (featureId: string) => void): void
  onFeatureContextMenu(cb: (featureId: string, lnglat: [number, number]) => void): void
  onFeatureDragEnd(cb: (featureId: string, geometry: unknown) => void): void
  startEdit(featureId: string): void
  stopEdit(): void

  // 工具与查询
  searchAndLocate(keyword: string): Promise<{ name: string; address: string; location: [number, number]; distance: number }[]>
  locateSearch(lng: number, lat: number, name: string): void
  clearSearchMarkers(): void
  locate(lng: number, lat: number, zoom?: number): void
  getCenter(): [number, number]
  getZoom(): number
  startMeasure(tool: 'distance' | 'area', onDone?: (result: { distance?: number; area?: number; geometry?: unknown }) => void): void
  stopDraw(): void

  // 底图
  setBaseLayer(type: MapBaseType): void
  getBaseLayer(): MapBaseType

  // 样式
  getStyleFor(feature: Feature): Record<string, unknown>
}