/** 地图服务工厂：若更换 MapLibre，只需实现 MapService 接口并在此切换。 */
import type { MapService, MapServiceOptions } from './MapService'
import { AmapMapService } from './AmapMapService'

let current: MapService | null = null

export function createMapService(options: MapServiceOptions): MapService {
  current = new AmapMapService(options)
  return current
}

export function getMapService(): MapService | null {
  return current
}