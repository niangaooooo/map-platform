"""WGS84 <-> GCJ-02 坐标转换（海外公开算法）。

高德地图使用 GCJ-02（火星坐标），GPS / 国际 GIS 数据使用 WGS84。
导入 WGS84 数据时转换为 GCJ-02 显示；原始数据保留备查。
"""
import math

PI = math.pi
_A = 6378245.0  # 长半轴
_EE = 0.00669342162296594323  # 偏心率平方


def _out_of_china(lng: float, lat: float) -> bool:
    return not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271)


def _transform_lat(x: float, y: float) -> float:
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * PI) + 40.0 * math.sin(y / 3.0 * PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * PI) + 320.0 * math.sin(y * PI / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lng(x: float, y: float) -> float:
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * PI) + 40.0 * math.sin(x / 3.0 * PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * PI) + 300.0 * math.sin(x / 30.0 * PI)) * 2.0 / 3.0
    return ret


def wgs84_to_gcj02(lng: float, lat: float) -> tuple[float, float]:
    """WGS84 -> GCJ-02。境外坐标直接返回。"""
    if _out_of_china(lng, lat):
        return lng, lat
    d_lat = _transform_lat(lng - 105.0, lat - 35.0)
    d_lng = _transform_lng(lng - 105.0, lat - 35.0)
    rad_lat = lat / 180.0 * PI
    magic = math.sin(rad_lat)
    magic = 1 - _EE * magic * magic
    sqrt_magic = math.sqrt(magic)
    d_lat = (d_lat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrt_magic) * PI)
    d_lng = (d_lng * 180.0) / (_A / sqrt_magic * math.cos(rad_lat) * PI)
    return lng + d_lng, lat + d_lat


def gcj02_to_wgs84(lng: float, lat: float) -> tuple[float, float]:
    """GCJ-02 -> WGS84（近似，精度 ~1m）。"""
    if _out_of_china(lng, lat):
        return lng, lat
    g_lng, g_lat = wgs84_to_gcj02(lng, lat)
    return lng * 2 - g_lng, lat * 2 - g_lat


def _convert(lng: float, lat: float, to_gcj: bool) -> tuple[float, float]:
    if to_gcj:
        return wgs84_to_gcj02(lng, lat)
    return gcj02_to_wgs84(lng, lat)


def transform_geometry(geometry: dict, to_gcj: bool = True) -> dict:
    """对 GeoJSON 几何做坐标系转换，返回新对象（不修改入参）。

    to_gcj=True 表示 WGS84 -> GCJ-02，False 表示 GCJ-02 -> WGS84。
    Circle 的 center 同样处理。
    """
    gt = geometry.get("type")
    if gt == "Point":
        coords = geometry.get("coordinates")
        if isinstance(coords, (list, tuple)) and len(coords) >= 2:
            x, y = _convert(coords[0], coords[1], to_gcj)
            return {"type": "Point", "coordinates": [x, y]}
    elif gt == "LineString":
        return {"type": "LineString", "coordinates": [_convert(p[0], p[1], to_gcj) for p in geometry.get("coordinates", [])]}
    elif gt == "Polygon":
        return {
            "type": "Polygon",
            "coordinates": [[_convert(p[0], p[1], to_gcj) for p in ring] for ring in geometry.get("coordinates", [])],
        }
    elif gt == "MultiPoint":
        return {"type": "MultiPoint", "coordinates": [_convert(p[0], p[1], to_gcj) for p in geometry.get("coordinates", [])]}
    elif gt == "MultiLineString":
        return {
            "type": "MultiLineString",
            "coordinates": [[_convert(p[0], p[1], to_gcj) for p in ln] for ln in geometry.get("coordinates", [])],
        }
    elif gt == "MultiPolygon":
        return {
            "type": "MultiPolygon",
            "coordinates": [
                [[_convert(p[0], p[1], to_gcj) for p in ring] for ring in poly]
                for poly in geometry.get("coordinates", [])
            ],
        }
    elif gt == "Circle":  # 自定义扩展：{center:[lng,lat], radius:米}
        center = geometry.get("center")
        if isinstance(center, (list, tuple)) and len(center) >= 2:
            x, y = _convert(center[0], center[1], to_gcj)
            return {"type": "Circle", "center": [x, y], "radius": geometry.get("radius", 0)}
    return geometry


def haversine_meters(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    """球面距离（米），用于附近点/圈内查询（GCJ-02 上近似可用）。"""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))
