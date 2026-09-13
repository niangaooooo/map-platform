/**
 * 高德地图 JS API 2.0 实现。
 * 引用的全局 AMap 由 index.html 动态加载（meta[name=amap-key] 提供 Key）。
 */
import type { CircleGeometry, Feature } from '@/types'
import type { MapBaseType, MapService, MapServiceOptions, MapToolType } from './MapService'

declare global {
  interface Window {
    AMap: any
  }
}

/** 标点自绘样式：彩色圆点 + 可绕圈摆放的名字（8 方向避让，保证不遮挡） */
let _pointCssInjected = false
function ensurePointStyle(): void {
  if (_pointCssInjected || typeof document === 'undefined') return
  _pointCssInjected = true
  const style = document.createElement('style')
  style.textContent = `
.amap-fp { position: relative; width: 20px; height: 20px; transform: translate(-50%, -50%); display: flex; align-items: center; justify-content: center; cursor: move; }
.amap-fp .fp-dot { width: 12px; height: 12px; border-radius: 50%; border: 2px solid #fff; box-shadow: 0 0 0 1px rgba(0,0,0,.22), 0 1px 3px rgba(0,0,0,.3); pointer-events: auto; flex-shrink: 0; }
.amap-fp .fp-name { position: absolute; visibility: hidden; white-space: nowrap; font-size: 12px; line-height: 18px; padding: 1px 7px; border-radius: 9px; background: rgba(255,255,255,.94); color: #333; border: 1px solid rgba(0,0,0,.14); box-shadow: 0 1px 4px rgba(0,0,0,.18); pointer-events: none; }
`
  document.head.appendChild(style)
}

const DEFAULT_CENTER: [number, number] = [113.264, 23.1991] // 广州


/** 要素是否被用户手动隐藏（标记写在 properties.hidden，随要素同步到其他协作者） */
export function isFeatureHidden(feature: Feature | null | undefined): boolean {
  const props = feature?.properties as Record<string, unknown> | undefined
  return !!props && props.hidden === true
}

/** 圆绑定的父标点 id（properties.parent_point_id，随要素同步） */
export function boundParentId(feature: Feature | null | undefined): string | undefined {
  const props = feature?.properties as Record<string, unknown> | undefined
  const v = props?.parent_point_id
  return typeof v === 'string' && v ? v : undefined
}

export class AmapMapService implements MapService {
  map: any = null
  private container: HTMLElement
  private amapKey: string
  private overlays = new Map<string, any>()
  private toolListeners: ((geometry: unknown, tool: MapToolType) => void)[] = []
  private clickListeners: ((featureId: string) => void)[] = []
  private contextListeners: ((featureId: string, lnglat: [number, number]) => void)[] = []
  private dragListeners: ((featureId: string, geometry: unknown) => void)[] = []
  private currentEdits: { featureId: string; editor: any } | null = null
  /** 标点拖动编辑模式：进入"点编辑"后，该标点才可拖动（避免日常误触移动位置） */
  private pointDragId: string | null = null
  /** 被用户手动隐藏的要素 id 集合（隐藏标记存在 feature.properties.hidden 里，便于多端同步） */
  private hiddenIds = new Set<string>()
  private drawTool: any = null
  private measureTool: any = null
  private searchService: any = null
  private placeSearch: any = null
  private baseLayer: any = null
  private satelliteLayers: { satellite: any; roadNet: any } | null = null

  private securityCode: string

  // 标点名字 label 避让所需：featureId → 名字 DOM 元素
  private pointNameEls = new Map<string, HTMLElement>()
  private hoveredPointIds = new Set<string>()
  private labelLayoutTimer: number | null = null

  constructor(private options: MapServiceOptions) {
    this.container = options.container
    this.amapKey = options.amapKey
    this.securityCode = options.securityCode || ''
  }

  async init(): Promise<void> {
    if (this.map) return
    await loadAmapScript(this.amapKey, this.securityCode)
    // 预加载绘图/测距/编辑所需插件（JS API 2.0 中这些均为可选插件，不加载则 new 报错）
    await loadAmapPlugins()
    this.map = new window.AMap.Map(this.container, {
      center: this.options.center ?? DEFAULT_CENTER,
      zoom: this.options.zoom ?? 13,
      resizeEnable: true,
    })
    // 调试挂点：便于端到端验证与排查（不暴露 Key）
    ;(window as any).__ammap = this.map
    ;(window as any).__amapService = this

    // 编辑态下点击地图空白处 → 结束编辑（用户提示"完成后点击其他区域保存"）。
    // 缺少该监听时，用户退出编辑后 CircleEditor/PolyEditor 仍挂载在画布上，
    // 圆形的半径引线和控制点会一直残留且无法删除。
    this.map.on('click', (e: any) => this.onMapClickEditExit(e))

    // 地图平移 / 缩放 / 尺寸变化后，标点名字 label 需要重新避让布局
    this.map.on('moveend', () => this.scheduleLabelLayout())
    this.map.on('zoomend', () => this.scheduleLabelLayout())
    this.map.on('resize', () => this.scheduleLabelLayout())

    // WebGL 上下文丢失（GPU 显存不足/驱动崩溃等）→ 销毁实例并让上层重建。
    // 高德 2.0 底图靠 WebGL 渲染，context 一丢瓦片就全空白、控制台刷
    // GL_OUT_OF_MEMORY / CONTEXT_LOST_WEBGL；不处理只能靠整页刷新恢复。
    this._onContextLost = (e: Event) => {
      e.preventDefault?.() // 允许浏览器尝试恢复（部分 GPU 可 restored）
      console.warn('[AmapMapService] WebGL context lost，尝试重建地图…')
      try {
        this.map?.destroy()
      } catch { /* ignore */ }
      this.map = null
      this.overlays.clear()
      this.pointNameEls.clear()
      this.hoveredPointIds.clear()
      this.options.onContextLost?.()
    }
    this.container.addEventListener('webglcontextlost', this._onContextLost)
  }

  /** 地图空白处点击：结束当前编辑；点击在编辑器自身控制点/画板上时忽略，避免打断拖拽 */
  private onMapClickEditExit(e: any): void {
    if (!this.currentEdits && !this.pointDragId) return
    const t = e?.originalEvent?.target as HTMLElement | null
    // 高德编辑器的控制点是 .amap-marker DOM；点中它们时保持编辑态
    if (t && (t.classList?.contains('amap-marker') || t.closest?.('.amap-marker'))) return
    this.stopEdit()
  }

  destroy(): void {
    this.stopEdit()
    if (this.labelLayoutTimer) {
      window.clearTimeout(this.labelLayoutTimer)
      this.labelLayoutTimer = null
    }
    this.pointNameEls.clear()
    this.hoveredPointIds.clear()
    if (this._onContextLost) {
      this.container.removeEventListener('webglcontextlost', this._onContextLost)
      this._onContextLost = null
    }
    try {
      this.map?.destroy()
    } catch { /* ignore */ }
    this.map = null
    this.overlays.clear()
  }

  private _onContextLost: ((e: Event) => void) | null = null

  // ---------- Overlay 管理 ----------
  setFeatures(features: Feature[]): void {
    this.clearAll()
    for (const f of features) {
      if (f.deleted_at) continue
      this.renderFeature(f)
    }
  }

  upsertFeature(feature: Feature): void {
    // 正在编辑该要素：就地更新几何，不重建 overlay ——
    // 拖拽保存后重建会导致编辑器控制点消失、拖拽被打断
    if (this.currentEdits?.featureId === feature.id) {
      if (feature.deleted_at) {
        this.stopEdit()
        this.removeFeature(feature.id)
        return
      }
      this.applyGeometryInPlace(feature)
      return
    }
    // 编辑其他要素时先结束当前编辑，避免编辑器残留控制点
    if (this.currentEdits) this.stopEdit()
    if (feature.deleted_at) {
      this.removeFeature(feature.id)
      return
    }
    // 若重建的正是"点编辑模式"下的标点，removeFeature 会清掉 pointDragId，
    // 这里先记住，remove+render 后恢复，让点编辑会话得以连续（拖完可再拖、直到点空白结束）。
    const wasPointDrag = this.pointDragId === feature.id ? feature.id : null
    this.removeFeature(feature.id)
    if (wasPointDrag) this.pointDragId = wasPointDrag
    this.renderFeature(feature)
  }

  /** 编辑中收到自身保存回传：就地更新几何，不复用 remove+render，
   *  否则重建 overlay 会断开正在进行的编辑器会话（控制点消失/编辑被打断） */
  private applyGeometryInPlace(feature: Feature): void {
    const overlay = this.overlays.get(feature.id)
    if (!overlay) {
      this.renderFeature(feature)
      return
    }
    const geo = feature.geometry_display as any
    if (!geo) return
    const type = overlay.getExtData?.().featureType
    try {
      if (type === 'point') overlay.setPosition?.(geo.coordinates)
      else if (type === 'circle') {
        overlay.setCenter?.(geo.center)
        overlay.setRadius?.(geo.radius)
      } else if (type === 'polyline' || type === 'polygon') overlay.setPath?.(geo.coordinates)
    } catch { /* ignore */ }
  }

  removeFeature(featureId: string): void {
    const overlay = this.overlays.get(featureId)
    if (overlay) {
      // 删除正在编辑的要素时先结束编辑器，防止控制点残留
      if (this.currentEdits?.featureId === featureId || this.pointDragId === featureId) this.stopEdit()
      this.map?.remove([overlay])
      this.overlays.delete(featureId)
    }
    this.pointNameEls.delete(featureId)
    this.hoveredPointIds.delete(featureId)
    this.scheduleLabelLayout()
  }

  clearAll(): void {
    if (this.overlays.size && this.map) this.map.remove([...this.overlays.values()])
    this.overlays.clear()
    this.pointNameEls.clear()
    this.hoveredPointIds.clear()
    this.scheduleLabelLayout()
  }

  fitView(ids?: string[]): void {
    try {
      if (ids && ids.length) {
        const overlays = ids.map(id => this.overlays.get(id)).filter(Boolean)
        if (overlays.length) this.map.setFitView(overlays)
      } else {
        this.map.setFitView(undefined, false, [40, 40, 40, 40])
      }
    } catch {
      /* ignore */
    }
  }

  setFeatureVisibility(featureId: string, visible: boolean): void {
    // 先记录状态：即使 overlay 尚未渲染（如后续才 setFeatures），也能保持隐藏意图
    if (visible) this.hiddenIds.delete(featureId)
    else this.hiddenIds.add(featureId)
    const overlay = this.overlays.get(featureId)
    if (overlay) this.applyVisibility(overlay, visible)
    // 父标点显隐变化 → 同步其绑定子圆的可见性
    const type = overlay?.getExtData?.()?.featureType
    if (type === 'point') this.syncBoundChildren(featureId)
    // 标点显隐变化后重新布局名字（隐藏时不占位，显示时恢复）
    if (type === 'point') this.scheduleLabelLayout()
  }

  /** 统一的显隐实现：AMap 2.0 各 overlay 提供 setVisible，部分版本只有 show/hide */
  private applyVisibility(overlay: any, visible: boolean): void {
    try {
      if (typeof overlay?.setVisible === 'function') overlay.setVisible(visible)
      else if (visible) overlay?.show?.()
      else overlay?.hide?.()
    } catch { /* ignore */ }
  }

  // ---------- 标点名字 8 方向避让 ----------
  // 名字是标点自绘 content 的一部分。多个标点距离近时名字会互相重叠，
  // 不再简单隐藏，而是让名字绕标点圆点在 上/右上/右下/下/左下/左上/右/左 8 个
  // 方向上寻找一个与其它名字不冲突的位置摆放，尽量保证所有名字可见且不遮挡。
  // 圆点直径 12（半径 6），名字外沿与圆点保持约 2px 间隙。
  private static readonly NAME_GAP = 8 // 6(圆点半径) + 2(间隙)

  /** 悬停时强制显示该标点名字（参与避让，但优先级最高） */
  private setPointNameHover(featureId: string, hovering: boolean): void {
    if (hovering) this.hoveredPointIds.add(featureId)
    else this.hoveredPointIds.delete(featureId)
    this.scheduleLabelLayout()
  }

  /** 名字可见性控制（visibility 不影响布局与测量） */
  private setPointNameVisible(featureId: string, visible: boolean): void {
    const el = this.pointNameEls.get(featureId)
    if (el) el.style.visibility = visible ? 'visible' : 'hidden'
  }

  /** 防抖调度：地图平移/缩放/增删标点后重新计算名字避让 */
  private scheduleLabelLayout(): void {
    if (this.labelLayoutTimer) window.clearTimeout(this.labelLayoutTimer)
    this.labelLayoutTimer = window.setTimeout(() => {
      this.labelLayoutTimer = null
      this.layoutPointNames()
    }, 120)
  }

  /** 计算候选摆放位置的 left/top（相对 20x20 锚点盒，中心即标点坐标） */
  private static nameCandidates(w: number, h: number): { left: number; top: number }[] {
    const r = AmapMapService.NAME_GAP
    const C = 10 // 20x20 盒中心
    const R = r // 名字与圆点之间的间距半径
    // 顺序：上、右上、右下、下、左下、左上、右、左（下方靠后的为"兜底"方向）
    const dirs: [number, number][] = [
      [0, -1], [1, -1], [1, 0], [1, 1], [0, 1], [-1, 1], [-1, 0], [-1, -1],
    ]
    const out: { left: number; top: number }[] = []
    for (const [dx, dy] of dirs) {
      if (dx === 0) {
        // 上/下：水平居中
        const top = dy < 0 ? C - h - R : C + R
        out.push({ left: C - w / 2, top })
      } else if (dy === 0) {
        // 左/右：垂直居中
        const left = dx > 0 ? C + R : C - w - R
        out.push({ left, top: C - h / 2 })
      } else {
        // 四角
        const left = dx > 0 ? C + R : C - w - R
        const top = dy < 0 ? C - h - R : C + R
        out.push({ left, top })
      }
    }
    return out
  }

  /** 贪心 8 方向避让布局：每个标点名字找一个不与已摆放名字重叠的候选方向 */
  private layoutPointNames(): void {
    const placed: { l: number; r: number; t: number; b: number }[] = []
    const overlap = (a: { l: number; r: number; t: number; b: number }, b: { l: number; r: number; t: number; b: number }) =>
      a.l < b.r && a.r > b.l && a.t < b.b && a.b > b.t
    const pad = 2
    const fits = (rect: { l: number; r: number; t: number; b: number }) =>
      !placed.some(p => overlap(
        { l: rect.l - pad, r: rect.r + pad, t: rect.t - pad, b: rect.b + pad },
        { l: p.l - pad, r: p.r + pad, t: p.t - pad, b: p.b + pad },
      ))

    // 收集标点顺序（保持渲染顺序，视觉稳定）
    const ids: string[] = []
    for (const [id, ov] of this.overlays) {
      const ext = ov.getExtData?.()
      if (ext?.featureType !== 'point') continue
      if (this.hiddenIds.has(id)) continue
      try {
        if (typeof ov.getVisible === 'function' && ov.getVisible() === false) continue
      } catch { /* ignore */ }
      ids.push(id)
    }
    // 悬停中的名字最先摆放（必定显示）
    const hovered = ids.filter(id => this.hoveredPointIds.has(id))
    const normal = ids.filter(id => !this.hoveredPointIds.has(id))
    const result = new Map<string, boolean>()

    const placeOne = (id: string, mustShow: boolean): boolean => {
      const el = this.pointNameEls.get(id)
      if (!el) return false
      const w = el.offsetWidth || 30
      const h = el.offsetHeight || 20
      const cands = AmapMapService.nameCandidates(w, h)
      for (const c of cands) {
        el.style.left = `${Math.round(c.left)}px`
        el.style.top = `${Math.round(c.top)}px`
        let rect: DOMRect
        try {
          rect = el.getBoundingClientRect()
        } catch {
          return false
        }
        if (rect.width < 2 || rect.height < 2) continue
        const box = { l: rect.left, r: rect.right, t: rect.top, b: rect.bottom }
        if (mustShow || fits(box)) {
          result.set(id, true)
          placed.push(box)
          return true
        }
      }
      // 8 个方向都放不下（极密集）：仅悬停必须显示，否则隐藏
      if (mustShow) {
        const c = cands[0]
        el.style.left = `${Math.round(c.left)}px`
        el.style.top = `${Math.round(c.top)}px`
        result.set(id, true)
        return true
      }
      result.set(id, false)
      return false
    }

    for (const id of hovered) placeOne(id, true)
    for (const id of normal) placeOne(id, false)
    for (const [id, visible] of result) this.setPointNameVisible(id, visible)
    // 不在 result 里的（无坐标/不可见区域）隐藏名字
    for (const id of this.pointNameEls.keys()) {
      if (!result.has(id)) this.setPointNameVisible(id, false)
    }
  }

  private renderFeature(feature: Feature): void {
    const AMap = window.AMap
    const geo = feature.geometry_display as any
    if (!geo) return
    const style = this.getStyleFor(feature)
    // 圆绑定父标点：渲染时若父标点已在地图上，圆心位置跟随父标点
    const parentId = boundParentId(feature)
    const parentPos = parentId ? this.getFeaturePosition(parentId) : null
    let overlay: any = null

    switch (feature.feature_type) {
      case 'point': {
        const pos = geo.coordinates
        ensurePointStyle()
        // 标点改为自绘：彩色圆点 + 上方名字。名字由 layoutPointLabels 做碰撞避让，
        // 避免多个标点挨得近时名字互相重叠看不清（原来用内置 label 无法避让）。
        const dotColor = (style.color as string) || '#FF5A5F'
        const content = document.createElement('div')
        content.className = 'amap-fp'
        const nameEl = document.createElement('span')
        nameEl.className = 'fp-name'
        nameEl.textContent = feature.name || ''
        const dotEl = document.createElement('span')
        dotEl.className = 'fp-dot'
        dotEl.style.background = dotColor
        content.appendChild(nameEl)
        content.appendChild(dotEl)
        overlay = new AMap.Marker({
          position: pos,
          content,
          // 默认不可拖动，避免日常误触移动标点；进入"编辑"后才可拖（见 startEdit）
          draggable: this.pointDragId === feature.id,
        })
        overlay.setExtData({ featureId: feature.id, featureType: feature.feature_type })
        // 记录名字 DOM，供碰撞避让
        this.pointNameEls.set(feature.id, nameEl)
        overlay.on('click', (e: any) => {
          e.stop?.()
          this.emitClick(feature.id)
        })
        overlay.on('rightclick', (e: any) => this.emitRightMenu(e, feature))
        overlay.on('mouseover', () => this.setPointNameHover(feature.id, true))
        overlay.on('mouseout', () => this.setPointNameHover(feature.id, false))
        overlay.on('dragstart', () => {
          // 点编辑模式下：拖动前结束其它要素的编辑器，避免控制点残留
          if (this.currentEdits) this.stopEdit()
        })
        overlay.on('dragend', (e: any) => {
          const pos = e.target?.getPosition?.()
          if (pos) this.emitDrag(feature.id, { type: 'Point', coordinates: [pos.getLng(), pos.getLat()] })
        })
        break
      }
      case 'circle': {
        const c = geo as CircleGeometry
        overlay = new AMap.Circle({
          // 绑定了父标点时，圆心显示在父标点位置（绑定关系以父标点为准）
          center: parentPos ?? c.center,
          radius: c.radius,
          strokeColor: style.strokeColor ?? style.color ?? '#FF5A5F',
          strokeWeight: style.strokeWeight ?? 3,
          // 默认无填充：只有圈；若用户指定了 fillColor 则保留
          fillColor: style.fillColor ?? 'transparent',
          fillOpacity: style.fillOpacity ?? 0,
        })
        overlay.on('click', (e: any) => {
          e.stop?.()
          this.emitClick(feature.id)
        })
        overlay.on('rightclick', (e: any) => this.emitRightMenu(e, feature))
        overlay.on('dblclick', (e: any) => e.stop?.())
        break
      }
      case 'polyline': {
        overlay = new AMap.Polyline({
          path: geo.coordinates,
          strokeColor: style.strokeColor ?? style.color ?? '#1677FF',
          strokeWeight: style.strokeWeight ?? 4,
        })
        overlay.on('rightclick', (e: any) => this.emitRightMenu(e, feature))
        break
      }
      case 'polygon': {
        overlay = new AMap.Polygon({
          path: geo.coordinates,
          strokeColor: style.strokeColor ?? style.color ?? '#FF5A5F',
          strokeWeight: style.strokeWeight ?? 3,
          fillColor: style.fillColor ?? 'transparent',
          fillOpacity: style.fillOpacity ?? 0,
        })
        overlay.on('rightclick', (e: any) => this.emitRightMenu(e, feature))
        break
      }
      default:
        return
    }

    overlay.setExtData?.({ featureId: feature.id, featureType: feature.feature_type, parentPointId: parentId ?? null })
    this.map.add(overlay)
    this.overlays.set(feature.id, overlay)

    // 尊重"隐藏"标记：用户隐藏过的要素加载后仍保持隐藏（标记存在 properties 里，多端同步）
    if (isFeatureHidden(feature)) {
      this.hiddenIds.add(feature.id)
      this.applyVisibility(overlay, false)
    } else {
      this.hiddenIds.delete(feature.id)
    }
    // 绑定联动：父标点被隐藏时，其子圆也隐藏
    if (parentId && this.hiddenIds.has(parentId) && !isFeatureHidden(feature)) {
      this.applyVisibility(overlay, false)
    }

    // 渲染标点后同步所有绑定的子圆（圆心跟随、可见性跟随）
    if (feature.feature_type === 'point') {
      this.syncBoundChildren(feature.id)
      // 标点渲染完成 → 重新做名字避让布局
      this.scheduleLabelLayout()
    }
  }

  /** 获取某要素 overlay 的当前位置（仅 point 有意义，circle 用圆心） */
  private getFeaturePosition(featureId: string): [number, number] | null {
    const ov = this.overlays.get(featureId)
    if (!ov) return null
    try {
      if (ov.getPosition?.()) {
        const p = ov.getPosition()
        return [p.getLng(), p.getLat()]
      }
      if (ov.getCenter?.()) {
        const p = ov.getCenter()
        return [p.getLng(), p.getLat()]
      }
    } catch { /* ignore */ }
    return null
  }

  /** 让所有绑定到 parentId 的子圆：圆心跟随父标点，可见性跟随父标点 */
  private syncBoundChildren(parentId: string): void {
    const parentPos = this.getFeaturePosition(parentId)
    const parentHidden = this.hiddenIds.has(parentId)
    for (const [id, ov] of this.overlays) {
      if (id === parentId) continue
      const ext = ov.getExtData?.() || {}
      if (ext.parentPointId !== parentId) continue
      if (parentPos && typeof ov.setCenter === 'function') {
        try {
          ov.setCenter(parentPos)
        } catch { /* ignore */ }
      }
      // 子圆可见 = 父可见 && 子自身没被隐藏
      const childHidden = this.hiddenIds.has(id)
      this.applyVisibility(ov, !parentHidden && !childHidden)
    }
  }

  /** 当 parentId 对应的圆变成孤儿（父被删除/解除绑定）时：移除 extData 里的绑定关系 */
  private detachBoundChildren(parentId: string): void {
    for (const [, ov] of this.overlays) {
      const ext = ov.getExtData?.()
      if (ext?.parentPointId === parentId) {
        try {
          ov.setExtData?.({ ...ext, parentPointId: null })
        } catch { /* ignore */ }
      }
    }
  }

  // ---------- 事件转发 ----------
  private emitClick(id: string) {
    this.clickListeners.forEach(fn => fn(id))
  }

  private emitRightMenu(e: any, feature: Feature) {
    // 用鼠标在屏幕上的位置（clientX/Y）而非经纬度，供右键菜单定位
    const oe = (e?.originalEvent ?? e) as MouseEvent | undefined
    const x = typeof oe?.clientX === 'number' ? oe.clientX : 0
    const y = typeof oe?.clientY === 'number' ? oe.clientY : 0
    this.contextListeners.forEach(fn => fn(feature.id, [x, y]))
  }

  private emitDrag(id: string, geometry: unknown) {
    this.dragListeners.forEach(fn => fn(id, geometry))
  }

  onFeatureClick(cb: (featureId: string) => void): void {
    this.clickListeners.push(cb)
  }

  onFeatureContextMenu(cb: (featureId: string, lnglat: [number, number]) => void): void {
    this.contextListeners.push(cb)
  }

  onFeatureDragEnd(cb: (featureId: string, geometry: unknown) => void): void {
    this.dragListeners.push(cb)
  }

  // ---------- 绘制工具 ----------
  setTool(tool: MapToolType, onResult?: (geometry: unknown, toolType: MapToolType) => void): void {
    this.stopDraw()
    this.stopMeasure()
    if (onResult) this.toolListeners = [onResult]

    if (tool === 'select') {
      this.map.setDefaultCursor('default')
      return
    }
    this.map.setDefaultCursor('crosshair')

    if (tool === 'point') {
      // 标点：点击地图直接回调
      this.onClickMode = true
      this.map.on('click', this.pointHandler)
      return
    }

    // 测距 / 测面积：走 RangingTool 标尺
    if (tool === 'measure' || tool === 'area') {
      this.startMeasure(tool === 'measure' ? 'distance' : 'area', (result) => {
        this.toolListeners.forEach(fn => fn(result, tool))
      })
      return
    }

    const AMap = window.AMap
    if (!AMap.MouseTool) {
      console.error('[AmapMapService] MouseTool 插件未就绪，请检查插件加载')
      return
    }
    const mouse = new AMap.MouseTool(this.map)
    this.drawTool = mouse
    const done = (geometry: unknown) => {
      this.toolListeners.forEach(fn => fn(geometry, tool))
    }

    // 绘制中右键结束当前图形（画线/画多边形时）
    const finishByRightClick = () => {
      try {
        // close(true) 触发 draw 完成当前绘制
        mouse.close(true)
      } catch { /* ignore */ }
    }
    this.contextMenuHandler = finishByRightClick
    this.map.on('rightclick', this.contextMenuHandler)

    if (tool === 'circle') {
      mouse.circle({
        strokeColor: '#FF5A5F',
        strokeWeight: 2,
        // 无填充，只有一个圈
        fillColor: 'transparent',
        fillOpacity: 0,
      })
      mouse.on('draw', (e: any) => {
        const c = e.obj
        done({ type: 'Circle', center: [c.getCenter().getLng(), c.getCenter().getLat()], radius: c.getRadius() })
      })
    } else if (tool === 'polyline') {
      mouse.polyline({
        strokeOpacity: 0.8,
        strokeColor: '#1677FF',
        strokeWeight: 4,
      })
      mouse.on('draw', (e: any) => {
        done({ type: 'LineString', coordinates: e.obj.getPath().map((p: any) => [p.getLng(), p.getLat()]) })
      })
    } else if (tool === 'polygon') {
      mouse.polygon({
        strokeColor: '#FF5A5F',
        strokeWeight: 2,
        fillColor: 'transparent',
        fillOpacity: 0,
      })
      mouse.on('draw', (e: any) => {
        const ring = e.obj.getPath().map((p: any) => [p.getLng(), p.getLat()])
        ring.push(ring[0])
        done({ type: 'Polygon', coordinates: [ring] })
      })
    }
  }

  private onClickMode = false
  private contextMenuHandler: (() => void) | null = null
  private pointHandler = (e: any) => {
    const lnglat = e.lnglat
    if (!lnglat) return
    this.toolListeners.forEach(fn => fn({ type: 'Point', coordinates: [lnglat.getLng(), lnglat.getLat()] }, 'point'))
  }

  stopDraw(): void {
    this.onClickMode = false
    if (this.map) {
      this.map.off('click', this.pointHandler)
      if (this.contextMenuHandler) {
        this.map.off('rightclick', this.contextMenuHandler)
        this.contextMenuHandler = null
      }
      this.map.setDefaultCursor('default')
    }
    if (this.drawTool) {
      try {
        this.drawTool.close?.()
      } catch {
        /* ignore */
      }
      this.drawTool = null
    }
  }

  // ---------- 编辑器 ----------
  private editSaveHandler: (() => void) | null = null
  /** 进入编辑前的 .amap-marker DOM 快照，用于清除高德关闭编辑后残留的控制点节点 */
  private editMarkerSnapshot: Element[] = []
  /** 拖拽保存防抖定时器：拖动过程 move/adjust 高频触发，仅保存最终几何 */
  private editSaveTimer: number | null = null

  startEdit(featureId: string): void {
    const overlay = this.overlays.get(featureId)
    if (!overlay) return
    // 若已在编辑其它要素，先结束（无论点编辑还是图形编辑器）
    if (this.currentEdits || this.pointDragId) this.stopEdit()

    const AMap = window.AMap
    const type = overlay.getExtData?.().featureType
    // 标点没有 AMap 官方拖拽编辑器，自建"点编辑模式"：
    // 仅编辑态允许拖动 marker（dragend 自动保存），退出后恢复不可拖。
    if (type === 'point') {
      this.pointDragId = featureId
      try {
        overlay.setDraggable(true)
      } catch { /* ignore */ }
      ;(window as any).__amapEditing = { featureId, editorType: 'point' }
      return
    }
    let editor: any = null
    if (type === 'circle') editor = new AMap.CircleEditor(this.map, overlay)
    else if (type === 'polyline') editor = new AMap.PolyEditor(this.map, overlay)
    else if (type === 'polygon') editor = new AMap.PolygonEditor(this.map, overlay)
    else return
    // 记录编辑前的 marker DOM，供关闭编辑后清理高德残留节点。
    // 必须在 editor.open() 之前采集：open() 会立刻创建编辑器控制点节点，
    // 若在 open() 之后采集，控制点会被算进快照，残留节点就清不掉。
    this.editMarkerSnapshot = Array.from(this.container.querySelectorAll('.amap-marker'))
    editor.open()
    this.currentEdits = { featureId, editor }
    ;(window as any).__amapEditing = { featureId, editorType: type }

    // 拖拽过程中的实时保存（防抖 400ms）。
    // 高德编辑器在"拖动圆心/半径控制点"期间派发 move/adjust 等事件，
    // 若只等 'end'（仅在 close() 时触发），拖完不发 end 就会丢修改——
    // 此前"圆拖动后刷新回原位"的根因即在于此。
    // 同时挂 moveend/adjustend 作为兜底，任何拖动结束方式都能触发保存。
    editor.on?.('move', this.scheduleEditSave)
    editor.on?.('adjust', this.scheduleEditSave)
    editor.on?.('moveend', this.scheduleEditSave)
    editor.on?.('adjustend', this.scheduleEditSave)

    // 编辑会话结束（close/end）→ 兜底提交当前几何（防抖未触发时也保存），再关闭编辑态
    const onEditEnd = () => {
      this.commitEditGeometry()
      this.stopEdit()
    }
    editor.on?.('end', onEditEnd) ?? (this.editSaveHandler = onEditEnd)
  }

  /** 读取当前编辑中的几何并回调保存（防抖提交 / stopEdit 前兜底提交） */
  private commitEditGeometry(): void {
    if (!this.currentEdits) return
    const eid = this.currentEdits.featureId
    const target = this.overlays.get(eid)
    if (!target) return
    const type = target.getExtData?.().featureType
    let geometry: unknown = null
    if (type === 'circle') {
      const c = target.getCenter()
      geometry = { type: 'Circle', center: [c.getLng(), c.getLat()], radius: target.getRadius() }
    } else if (type === 'polyline' || type === 'polygon') {
      const path = target.getPath?.() ?? []
      const coords = path.map((p: any) => [p.getLng(), p.getLat()])
      geometry = type === 'polygon'
        ? { type: 'Polygon', coordinates: [coords.concat([coords[0]])] }
        : { type: 'LineString', coordinates: coords }
    }
    // 回传几何（MapView.handleDragEnd 会保存到后端并刷新 overlay）
    if (geometry) this.emitDrag(eid, geometry)
  }

  private scheduleEditSave = (): void => {
    if (this.editSaveTimer) window.clearTimeout(this.editSaveTimer)
    this.editSaveTimer = window.setTimeout(() => {
      this.editSaveTimer = null
      this.commitEditGeometry()
    }, 400)
  }

  stopEdit(): void {
    // 退出"点编辑模式"：恢复标点不可拖，避免下次误触
    if (this.pointDragId) {
      const ov = this.overlays.get(this.pointDragId)
      if (ov) {
        try {
          ov.setDraggable(false)
        } catch { /* ignore */ }
      }
      this.pointDragId = null
      ;(window as any).__amapEditing = null
    }
    // 退出编辑前先提交当前几何（防抖定时器未触发时也兜底），保证拖动结果一定保存
    if (this.editSaveTimer) {
      window.clearTimeout(this.editSaveTimer)
      this.editSaveTimer = null
      this.commitEditGeometry()
    }
    if (this.currentEdits) {
      // 关键：先把 currentEdits 置空再 close()。
      // 高德 editor.close() 会触发 'end' 事件，若 currentEdits 仍存在，
      // onEditEnd 重入 → 同一几何 commitEditGeometry 多次 → 对同一旧 version
      // 并发发多个 PATCH → 除首个外全部 409"其他用户修改" + 保存失败。
      const editor = this.currentEdits.editor
      this.currentEdits = null

      // ① 先清理编辑期间新增的编辑器控制点 DOM（高德 close() 后不清理自己的节点）。
      //    必须在 editor.close() 之前做：close() 会让高德重建 marker 图层，
      //    重建后要素标点的 DOM 是新节点、不在快照里，此时再按快照比对删除会把
      //    要素标点一并误删 —— 表现为"编辑完圆后标点消失，但图层树仍有数据，
      //    重新进入项目才恢复"。close() 之前比对时标点 DOM 仍是快照中的原始节点，安全。
      this.removeEditorResidualNodes()
      try {
        editor.close()
      } catch {
        /* ignore */
      }
      // ② 编辑器关闭后统一重挂一次要素 overlay，确保高德重建图层后所有要素仍然可见，
      //    同时按 hidden 标记恢复各要素的显示/隐藏状态。
      this.remountOverlays()
    }
    this.editMarkerSnapshot = []
    this.editSaveHandler = null
    ;(window as any).__amapEditing = null
  }

  /** 清理本次编辑新增的 .amap-marker 节点（编辑器的半径线/控制点），保留编辑前已存在的要素标点 */
  private removeEditorResidualNodes(): void {
    if (!this.container) return
    const snapshot = new Set(this.editMarkerSnapshot)
    let residual: Element[] = []
    try {
      residual = Array.from(this.container.querySelectorAll('.amap-marker')).filter(el => !snapshot.has(el))
    } catch {
      return
    }
    for (const el of residual) {
      try {
        el.remove()
      } catch { /* ignore */ }
    }
  }

  /** 重新挂载全部要素 overlay。
   *  editor.close() 会重建高德图层，个别要素（尤其 Marker 标点）可能因此丢失显示；
   *  重挂一次可保证全部要素仍在地图上，并按 hidden 标记恢复可见性。 */
  private remountOverlays(): void {
    if (!this.map || this.overlays.size === 0) return
    const entries = [...this.overlays.entries()]
    try {
      this.map.remove(entries.map(([, ov]) => ov))
    } catch { /* ignore */ }
    for (const [id, ov] of entries) {
      try {
        this.map.add(ov)
      } catch { /* ignore */ }
      // 重挂后高德会恢复为可见，这里按记录重新应用隐藏状态
      if (this.hiddenIds.has(id)) this.applyVisibility(ov, false)
    }
    // 重挂后重新建立绑定关系：子圆圆心/可见性跟随父标点
    this.syncAllBindings()
  }

  /** 遍历所有"点"要素，把它们的绑定子圆同步一遍（圆心 + 可见性） */
  private syncAllBindings(): void {
    for (const [id, ov] of this.overlays) {
      const ext = ov.getExtData?.()
      if (ext?.featureType === 'point') this.syncBoundChildren(id)
    }
  }

  // ---------- 搜索 ----------
  // 注意：POI 搜索统一走后端 /amap-proxy REST 代理（高德 JS API 2.0 的 PlaceSearch
  // 插件在部分 Key/域名配置下不稳定，REST 通道最可靠且 Key 不暴露）
  async searchAndLocate(keyword: string): Promise<{ name: string; address: string; location: [number, number]; distance: number }[]> {
    const { amapApi } = await import('@/api')
    const center = this.getCenter()
    const zoom = this.getZoom()
    // 视野半径估算：zoom 越高视野越小；zoom 13 时约为 5km，每升 1 级减半
    const radiusKm = Math.max(1, Math.round(5200 / 2 ** Math.max(0, zoom - 13)))
    const radius = radiusKm * 1000
    try {
      // location + radius 让高德优先返回当前视野附近的结果
      const data = await amapApi.search(keyword, undefined, center, radius)
      if (data.status !== '1' || !Array.isArray(data.pois)) return []
      const results = data.pois
        .filter((p) => p.location)
        .map((p) => {
          const [lng, lat] = String(p.location).split(',').map(Number)
          const dist = this.haversine(center[0], center[1], lng, lat)
          return { name: p.name, address: p.address || '', location: [lng, lat] as [number, number], distance: dist }
        })
      // 视野内优先，其余按距离升序（优先级下调）
      return results.sort((a, b) => {
        const aIn = a.distance <= radius
        const bIn = b.distance <= radius
        if (aIn !== bIn) return aIn ? -1 : 1
        return a.distance - b.distance
      })
    } catch (e) {
      console.error('[searchAndLocate] REST 搜索失败', e)
      return []
    }
  }

  private haversine(lng1: number, lat1: number, lng2: number, lat2: number): number {
    const R = 6371000
    const toRad = (d: number) => (d * Math.PI) / 180
    const dLat = toRad(lat2 - lat1)
    const dLng = toRad(lng2 - lng1)
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2
    return 2 * R * Math.asin(Math.sqrt(a))
  }

  // 搜索结果临时标记（点击后在地图上标出该地址）
  private searchMarkers: any[] = []

  /** 搜索定位：飞至目标点并显示一个可关闭的标记 */
  locateSearch(lng: number, lat: number, name: string): void {
    this.locate(lng, lat, 15)
    const AMap = window.AMap
    this.clearSearchMarkers()
    const marker = new AMap.Marker({
      position: [lng, lat],
      title: name,
      label: { content: name || '搜索结果', direction: 'top', offset: new AMap.Pixel(0, -26) },
      // 醒目样式：默认红色圆点
    })
    marker.on('click', () => this.clearSearchMarkers())
    this.map.add(marker)
    this.searchMarkers = [marker]
  }

  clearSearchMarkers(): void {
    if (this.searchMarkers.length) {
      this.map.remove(this.searchMarkers)
      this.searchMarkers = []
    }
  }

  locate(lng: number, lat: number, zoom = 15): void {
    this.map.setZoomAndCenter(zoom, [lng, lat])
  }

  getCenter(): [number, number] {
    const c = this.map.getCenter()
    return [c.getLng(), c.getLat()]
  }

  getZoom(): number {
    return this.map.getZoom()
  }

  // ---------- 底图切换 ----------
  setBaseLayer(type: MapBaseType): void {
    if (!this.map) return
    const AMap = window.AMap
    // 卫星 = 卫星影像 + 路网标注叠加（高德 JS API 内置图层，无需插件）
    if (type === 'satellite') {
      if (!this.satelliteLayers) {
        this.satelliteLayers = {
          satellite: new AMap.TileLayer.Satellite(),
          roadNet: new AMap.TileLayer.RoadNet(),
        }
      }
      if (this.baseLayer) this.map.remove([this.baseLayer])
      this.map.add([this.satelliteLayers.satellite])
      this.map.add([this.satelliteLayers.roadNet])
      this.baseLayer = this.satelliteLayers.satellite
    } else {
      if (this.satelliteLayers) {
        this.map.remove([this.satelliteLayers.satellite, this.satelliteLayers.roadNet])
      }
      // 恢复默认路网底图（remove 卫星层后原生底图自动可见）
      this.baseLayer = null
    }
  }

  getBaseLayer(): MapBaseType {
    return this.baseLayer ? 'satellite' : 'normal'
  }

  // ---------- 测距 / 测面积 ----------
  startMeasure(tool: 'distance' | 'area', onDone?: (result: { distance?: number; area?: number; geometry?: unknown }) => void): void {
    this.stopMeasure()
    const AMap = window.AMap
    if (!AMap.RangingTool) {
      console.error('[AmapMapService] RangingTool 插件未就绪，请检查插件加载')
      return
    }
    const measure = new AMap.RangingTool(this.map)
    this.measureTool = measure
    // 每次测量结束自动拾取结果
    const complete = (e: any) => {
      const result: { distance?: number; area?: number; geometry?: unknown } = {}
      if (tool === 'distance') {
        // RangingTool 在 end 事件中给出总距离（米）
        result.distance = e.distance ?? e.overlays?.[0]?.getLength?.()
        if (e.overlays?.[0]?.getPath?.()) {
          result.geometry = { type: 'LineString', coordinates: e.overlays[0].getPath().map((p: any) => [p.getLng(), p.getLat()]) }
        }
      } else {
        // 面积：RangingTool 不直接给 area，用顶点数 × 尺度近似，此处直接回调空结果由上层展示
        result.area = e.area ?? undefined
        if (e.overlays?.[0]?.getPath?.()) {
          result.geometry = { type: 'Polygon', coordinates: [e.overlays[0].getPath().map((p: any) => [p.getLng(), p.getLat()])] }
        }
      }
      onDone?.(result)
      // 测量完成自动关闭，便于下一次
      try {
        measure.turnOff()
      } catch { /* ignore */ }
    }
    measure.on('end', complete)
    measure.turnOn()
  }

  private circleArea(overlay: any): number {
    const path = overlay.getPath?.() ?? []
    if (path.length < 3) return 0
    let a = 0
    for (let i = 0; i < path.length; i++) {
      const p1 = path[i]
      const p2 = path[(i + 1) % path.length]
      a += p1.getLng() * p2.getLat() - p2.getLng() * p1.getLat()
    }
    return Math.abs(a / 2) * 110000 * 92000 // 粗略换算平方米（略，仅示意）
  }

  stopMeasure(): void {
    if (this.measureTool) {
      try {
        this.measureTool.turnOff?.()
      } catch {
        /* ignore */
      }
      this.measureTool = null
    }
  }

  // ---------- 样式 ----------
  getStyleFor(feature: Feature): Record<string, unknown> {
    return { ...((feature.style || {}) as Record<string, unknown>) }
  }
}

let amapPromise: Promise<void> | null = null

function loadAmapScript(key: string, securityCode?: string): Promise<void> {
  if (window.AMap) return Promise.resolve()
  if (amapPromise) return amapPromise
  amapPromise = new Promise((resolve, reject) => {
    // JS API 2.0 需要 securityJsCode（安全密钥），必须在加载脚本前通过
    // window._AMapSecurityConfig 注入，否则底图瓦片静默拒绝渲染（只出 logo 不出瓦片）。
    if (securityCode) {
      ;(window as any)._AMapSecurityConfig = { securityJsCode: securityCode }
    }
    const script = document.createElement('script')
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(key)}`
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => {
      amapPromise = null
      reject(new Error('高德地图脚本加载失败'))
    }
    document.head.appendChild(script)
  })
  return amapPromise
}

const REQUIRED_PLUGINS = [
  'AMap.MouseTool', // 画圆 / 画线 / 画多边形
  'AMap.RangingTool', // 测距 / 测面积
  'AMap.CircleEditor', // 编辑圆
  'AMap.PolyEditor', // 编辑线
  'AMap.PolygonEditor', // 编辑多边形
]

let pluginsPromise: Promise<void> | null = null

/** JS API 2.0 插件预加载：MouseTool / RangingTool / 各类 Editor 必须显式引入才可用 */
function loadAmapPlugins(): Promise<void> {
  if (!window.AMap) return Promise.reject(new Error('高德地图脚本未加载'))
  if (pluginsPromise) return pluginsPromise
  pluginsPromise = new Promise((resolve) => {
    window.AMap.plugin(REQUIRED_PLUGINS, () => resolve())
  })
  return pluginsPromise
}