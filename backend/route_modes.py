import math
from typing import List, Tuple, Dict


class RouteModeSelector:
    """Выбор типа маршрута с динамическим обходом опасностей"""

    MODES = {
        'fastest': {
            'name': 'Самый быстрый',
            'icon': '⚡',
            'description': 'Минимальное время в пути',
            'speed_factor': 1.3,
            'fuel_factor': 1.4,
            'safety_factor': 0.6,
            'preferred_modes': ['diesel', 'diesel']
        },
        'economical': {
            'name': 'Экономичный',
            'icon': '💰',
            'description': 'Минимальный расход топлива',
            'speed_factor': 0.85,
            'fuel_factor': 0.6,
            'safety_factor': 0.8,
            'preferred_modes': ['sail', 'battery']
        },
        'safe': {
            'name': 'Безопасный',
            'icon': '🛡️',
            'description': 'Обход опасных зон',
            'speed_factor': 0.8,
            'fuel_factor': 1.15,
            'safety_factor': 1.5,
            'preferred_modes': ['battery', 'diesel']
        }
    }

    def __init__(self):
        self.weather_service = None
        self.hazard_avoidance_distance = 100

    def set_weather_service(self, weather_service):
        self.weather_service = weather_service

    def optimize_route_for_mode(self,
                                original_route: List[Tuple[float, float]],
                                mode: str,
                                weather_data: List[Dict] = None,
                                risk_level: str = 'low') -> Tuple[List[Tuple[float, float]], Dict]:
        if mode not in self.MODES:
            mode = 'economical'

        mode_config = self.MODES[mode]

        if len(original_route) < 2:
            return original_route, {'adjustments': []}

        optimized_route = original_route.copy()
        adjustments = []

        if mode == 'safe' and risk_level == 'high' and weather_data:
            optimized_route, hazard_adjustments = self._create_safe_detour(
                original_route, weather_data
            )
            adjustments.extend(hazard_adjustments)
            adjustments.append(
                f"🛡️ Маршрут изменен для обхода опасных зон (дистанция обхода: {self.hazard_avoidance_distance} км)")

        elif mode == 'safe' and risk_level == 'medium':
            optimized_route, hazard_adjustments = self._moderate_detour(
                original_route, weather_data
            )
            adjustments.extend(hazard_adjustments)

        elif mode == 'economical' and risk_level == 'high':
            adjustments.append("⚠️ Высокий уровень риска! Рекомендуется временно снизить скорость на 15%")
            adjustments.append("💡 Используйте роторы Флеттнера при попутном ветре для экономии")

        if mode == 'fastest':
            optimized_route = self._simplify_route(optimized_route, tolerance=0.3)
            adjustments.append("🚀 Прямой маршрут для максимальной скорости")
            adjustments.append(f"⚡ Рекомендуемая скорость: {12.5 * mode_config['speed_factor']:.1f} узлов")

        elif mode == 'economical':
            optimized_route = self._smooth_route(optimized_route)
            adjustments.append("📉 Сглаженный маршрут для экономии топлива")
            adjustments.append("💰 Оптимальная скорость: 10-11 узлов для минимального расхода")
            adjustments.append("🌬️ При попутном ветре используйте роторы Флеттнера (экономия до 30%)")
            adjustments.append("🔋 В портах заряжайте батареи по ночным тарифам")

        return optimized_route, {
            'mode': mode,
            'mode_name': mode_config['name'],
            'mode_icon': mode_config['icon'],
            'adjustments': adjustments,
            'speed_factor': mode_config['speed_factor'],
            'fuel_factor': mode_config['fuel_factor'],
            'safety_factor': mode_config['safety_factor'],
            'preferred_modes': mode_config['preferred_modes']
        }

    def _create_safe_detour(self, route: List[Tuple[float, float]],
                            weather_data: List[Dict]) -> Tuple[List[Tuple[float, float]], List[str]]:
        if not weather_data:
            return route, []

        adjustments = []
        hazard_zones = []

        for w in weather_data:
            lat, lon = w.get('lat'), w.get('lon')
            if not lat or not lon:
                continue

            is_hazard = False
            hazard_desc = []

            if w.get('wind_speed', 0) > 18:
                is_hazard = True
                hazard_desc.append(f"ветер {w['wind_speed']} м/с")
            if w.get('wave_height', 0) > 3.5:
                is_hazard = True
                hazard_desc.append(f"волны {w['wave_height']} м")
            if w.get('weather_main') in ['Thunderstorm', 'Storm', 'Squall', 'Hurricane']:
                is_hazard = True
                hazard_desc.append("шторм")

            if is_hazard:
                hazard_zones.append({
                    'lat': lat,
                    'lon': lon,
                    'description': ', '.join(hazard_desc),
                    'wind': w.get('wind_speed', 0),
                    'wave': w.get('wave_height', 0)
                })

        if not hazard_zones:
            return route, ["Опасных зон не обнаружено"]

        adjustments.append(f"⚠️ Обнаружено {len(hazard_zones)} опасных зон")

        detour_route = []

        for i, point in enumerate(route):
            lat, lon = point
            is_hazardous = False
            nearest_hazard_dist = float('inf')
            nearest_hazard = None

            for hazard in hazard_zones:
                dist = self._haversine_distance(lat, lon, hazard['lat'], hazard['lon'])
                if dist < self.hazard_avoidance_distance:
                    is_hazardous = True
                    if dist < nearest_hazard_dist:
                        nearest_hazard_dist = dist
                        nearest_hazard = hazard

            if is_hazardous and nearest_hazard:
                if 0 < i < len(route) - 1:
                    prev_lat, prev_lon = route[i - 1]
                    next_lat, next_lon = route[i + 1]
                    detour_lat, detour_lon = self._calculate_detour_point(
                        lat, lon, prev_lat, prev_lon, next_lat, next_lon, nearest_hazard
                    )
                    detour_route.append((detour_lat, detour_lon))
                    adjustments.append(f"🔄 Обход опасной зоны: {nearest_hazard['description']}")
                else:
                    continue
            else:
                detour_route.append(point)

        if len(detour_route) < 2:
            adjustments.append("⚠️ Невозможно полностью обойти опасные зоны, соблюдайте осторожность")
            return route, adjustments

        return detour_route, adjustments

    def _calculate_detour_point(self, lat, lon, prev_lat, prev_lon, next_lat, next_lon, hazard):
        dx = lon - hazard['lon']
        dy = lat - hazard['lat']

        length = math.sqrt(dx * dx + dy * dy)
        if length > 0:
            dx /= length
            dy /= length

        detour_distance_deg = 1.0

        detour_lat1 = lat + dy * detour_distance_deg
        detour_lon1 = lon - dx * detour_distance_deg

        detour_lat2 = lat - dy * detour_distance_deg
        detour_lon2 = lon + dx * detour_distance_deg

        dist1 = self._haversine_distance(detour_lat1, detour_lon1, hazard['lat'], hazard['lon'])
        dist2 = self._haversine_distance(detour_lat2, detour_lon2, hazard['lat'], hazard['lon'])

        if dist1 > dist2:
            return detour_lat1, detour_lon1
        else:
            return detour_lat2, detour_lon2

    def _moderate_detour(self, route: List[Tuple[float, float]],
                         weather_data: List[Dict]) -> Tuple[List[Tuple[float, float]], List[str]]:
        if not weather_data:
            return route, []

        adjustments = []
        critical_zones = []

        for w in weather_data:
            if w.get('weather_main') in ['Thunderstorm', 'Storm', 'Hurricane']:
                critical_zones.append((w.get('lat'), w.get('lon')))
                adjustments.append(f"⚠️ Обход шторма на {self.hazard_avoidance_distance} км")

        if not critical_zones:
            return route, ["Погодные условия в пределах нормы"]

        detour_route = []
        for point in route:
            lat, lon = point
            is_critical = False

            for cz_lat, cz_lon in critical_zones:
                dist = self._haversine_distance(lat, lon, cz_lat, cz_lon)
                if dist < self.hazard_avoidance_distance / 2:
                    is_critical = True
                    break

            if is_critical:
                detour_route.append((lat + 0.3, lon + 0.3))
            else:
                detour_route.append(point)

        return detour_route, adjustments

    def _simplify_route(self, route: List[Tuple[float, float]], tolerance: float = 0.5) -> List[Tuple[float, float]]:
        if len(route) <= 2:
            return route

        simplified = [route[0]]

        for i in range(1, len(route) - 1):
            prev = route[i - 1]
            curr = route[i]
            next_pt = route[i + 1]
            deviation = self._point_line_distance(curr, prev, next_pt)

            if deviation > tolerance:
                simplified.append(curr)

        simplified.append(route[-1])
        return simplified

    def _smooth_route(self, route: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        if len(route) < 3:
            return route

        smoothed = [route[0]]

        for i in range(1, len(route) - 1):
            lat1, lon1 = route[i - 1]
            lat2, lon2 = route[i]
            lat3, lon3 = route[i + 1]

            smoothed_lat = (lat1 + lat2 + lat3) / 3
            smoothed_lon = (lon1 + lon2 + lon3) / 3
            smoothed.append((smoothed_lat, smoothed_lon))

        smoothed.append(route[-1])
        return smoothed

    def _point_line_distance(self, point, line_start, line_end) -> float:
        lat, lon = point
        lat1, lon1 = line_start
        lat2, lon2 = line_end

        if lat1 == lat2 and lon1 == lon2:
            return self._haversine_distance(lat, lon, lat1, lon1)

        x = math.radians(lon)
        y = math.radians(lat)
        x1 = math.radians(lon1)
        y1 = math.radians(lat1)
        x2 = math.radians(lon2)
        y2 = math.radians(lat2)

        dx = x2 - x1
        dy = y2 - y1

        if dx == 0 and dy == 0:
            return self._haversine_distance(lat, lon, lat1, lon1)

        t = ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)

        if t < 0:
            closest = (x1, y1)
        elif t > 1:
            closest = (x2, y2)
        else:
            closest = (x1 + t * dx, y1 + t * dy)

        closest_lat = math.degrees(closest[1])
        closest_lon = math.degrees(closest[0])

        return self._haversine_distance(lat, lon, closest_lat, closest_lon)

    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return R * 2 * math.asin(math.sqrt(a))


route_mode_selector = RouteModeSelector()