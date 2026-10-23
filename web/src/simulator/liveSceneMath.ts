const METRES_PER_DEGREE = 111_320

export function toLocalNed(
  lat_deg: number,
  lon_deg: number,
  originLat_deg: number,
  originLon_deg: number,
): { north_m: number; east_m: number } {
  const originLat_rad = originLat_deg * Math.PI / 180
  return {
    north_m: (lat_deg - originLat_deg) * METRES_PER_DEGREE,
    east_m: (lon_deg - originLon_deg) * METRES_PER_DEGREE * Math.cos(originLat_rad),
  }
}
