// 与后端 Pydantic schemas 对应的类型定义

export type Role = 'owner' | 'admin' | 'editor' | 'viewer'
export type FeatureType = 'point' | 'circle' | 'polyline' | 'polygon'
export type CoordinateSystem = 'GCJ02' | 'WGS84'

export interface User {
  id: string
  username: string
  email: string
  display_name: string
  is_active: boolean
  created_at: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface Project {
  id: string
  name: string
  description: string
  owner_id: string
  owner_name?: string
  default_center: number[] | null
  default_zoom: number
  created_at: string
  updated_at: string
  role?: Role
}

export interface ProjectStats {
  feature_count: number
  folder_count: number
  member_count: number
  last_updated: string | null
}

export interface ProjectDetail extends Project {
  role: Role
  stats: ProjectStats
}

export interface Member {
  user_id: string
  username: string
  display_name: string
  email: string
  role: Role
  joined_at: string
}

export interface Folder {
  id: string
  project_id: string
  parent_id: string | null
  name: string
  sort_order: number
  visible: boolean
  created_at: string
  updated_at: string
}

export interface Category {
  id: string
  project_id: string
  name: string
  color: string
  icon: string
  sort_order: number
}

export interface Feature {
  id: string
  project_id: string
  folder_id: string | null
  category_id: string | null
  name: string
  feature_type: FeatureType
  geometry_display: Record<string, unknown> | CircleGeometry | null
  coordinate_system_display: CoordinateSystem
  geometry_original: Record<string, unknown> | null
  coordinate_system_original: CoordinateSystem | null
  properties: Record<string, unknown>
  style: FeatureStyle
  version: number
  created_by: string
  updated_by: string
  created_at: string
  updated_at: string
  deleted_at: string | null
}

export interface CircleGeometry {
  type: 'Circle'
  center: [number, number]
  radius: number
}

export interface FeatureStyle {
  color?: string
  fillColor?: string
  fillOpacity?: number
  strokeColor?: string
  strokeWeight?: number
  icon?: string
}

export interface FeatureVersion {
  id: string
  feature_id: string
  version: number
  geometry: Record<string, unknown> | null
  properties: Record<string, unknown> | null
  style: Record<string, unknown> | null
  name: string
  created_by: string
  created_at: string
}

export interface AuditLogEntry {
  id: string
  action: string
  target_type: string
  target_id: string | null
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  created_at: string
  username: string | null
  user_display_name: string | null
}

export interface NearbyResult {
  feature_id: string
  name: string
  feature_type: FeatureType
  distance_m: number
  category_id: string | null
}

export interface ImportResult {
  created: number
  skipped: number
  errors: { name: string; error: string }[]
}

// ---------- WebSocket 事件 ----------
export interface WsEnvelope {
  event: string
  project_id: string
  user_id: string | null
  data: Record<string, unknown>
}

export interface OnlineMember {
  id: string
  username: string
  display_name: string
  ts: string
}

export interface EditLock {
  user_id: string
  username: string
  display_name: string
}