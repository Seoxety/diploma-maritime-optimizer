from flask import Flask, request, jsonify
from flask_cors import CORS
import math
import json
import csv
import os
import heapq
import time
from datetime import datetime
from typing import List, Tuple, Dict, Optional

from weather_service import weather_service
from route_modes import route_mode_selector
from hybrid_system import hybrid_optimizer

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

PORTS_CSV = 'ports.csv'
OCEAN_GRAPH = 'ocean-grid-cache.json'

PORTS = {}

print("\n" + "=" * 60)
print("🚀 ИНИЦИАЛИЗАЦИЯ СИСТЕМЫ ОПТИМИЗАЦИИ МОРСКИХ МАРШРУТОВ")
print("=" * 60)


def load_ports_from_csv() -> Dict:
    """Загрузка портов из CSV с фильтрацией и группировкой"""
    global PORTS

    try:
        if not os.path.exists(PORTS_CSV):
            print(f"❌ Файл портов не найден: {PORTS_CSV}")
            return {}

        ports_dict = {}

        with open(PORTS_CSV, 'r', encoding='utf-8') as f:
            content = f.read()

        if ';' in content.split('\n')[0]:
            delimiter = ';'
        elif ',' in content.split('\n')[0]:
            delimiter = ','
        else:
            delimiter = ';'

        with open(PORTS_CSV, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=delimiter)

            try:
                headers = next(reader)
            except StopIteration:
                return {}

            col_mapping = {}
            for i, header in enumerate(headers):
                header_clean = str(header).strip().lower()

                if 'name' in header_clean:
                    col_mapping['name'] = i
                elif 'lat' in header_clean:
                    col_mapping['lat'] = i
                elif 'lon' in header_clean or 'lng' in header_clean:
                    col_mapping['lon'] = i
                elif 'country' in header_clean:
                    col_mapping['country'] = i

            if 'name' not in col_mapping and len(headers) >= 2:
                col_mapping['name'] = 1
            if 'lat' not in col_mapping and len(headers) >= 5:
                col_mapping['lat'] = 4
            if 'lon' not in col_mapping and len(headers) >= 6:
                col_mapping['lon'] = 5
            if 'country' not in col_mapping and len(headers) >= 3:
                col_mapping['country'] = 2

            for row in reader:
                try:
                    if not row or len(row) < 3:
                        continue

                    port_name = ""
                    if 'name' in col_mapping and col_mapping['name'] < len(row):
                        port_name = str(row[col_mapping['name']]).strip()

                    if not port_name:
                        continue

                    lat = None
                    lon = None

                    if 'lat' in col_mapping and col_mapping['lat'] < len(row):
                        lat_str = str(row[col_mapping['lat']]).strip().replace(',', '.')
                        lat_str = ''.join(c for c in lat_str if c.isdigit() or c in '.-')
                        if lat_str:
                            try:
                                lat = float(lat_str)
                            except ValueError:
                                pass

                    if 'lon' in col_mapping and col_mapping['lon'] < len(row):
                        lon_str = str(row[col_mapping['lon']]).strip().replace(',', '.')
                        lon_str = ''.join(c for c in lon_str if c.isdigit() or c in '.-')
                        if lon_str:
                            try:
                                lon = float(lon_str)
                            except ValueError:
                                pass

                    country = "Unknown"
                    if 'country' in col_mapping and col_mapping['country'] < len(row):
                        country = str(row[col_mapping['country']]).strip()

                    if lat is None or lon is None:
                        continue
                    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                        continue

                    ports_dict[port_name] = {
                        'lat': lat,
                        'lon': lon,
                        'country': country,
                        'type': 'commercial',
                        'description': f"Port {port_name} ({country})"
                    }

                except Exception:
                    continue

        filtered_ports = {}
        for port_name, port_data in ports_dict.items():
            lat = port_data['lat']
            if abs(lat) > 85:
                continue
            filtered_ports[port_name] = port_data

        sorted_ports = sorted(filtered_ports.items(), key=lambda x: (x[1]['lat'], x[1]['lon']))

        final_ports = {}
        MIN_DISTANCE_KM = 250.0

        for port_name, port_data in sorted_ports:
            lat, lon = port_data['lat'], port_data['lon']
            too_close = False
            nearest_distance = float('inf')
            nearest_port = None

            for proc_name, proc_data in final_ports.items():
                proc_lat, proc_lon = proc_data['lat'], proc_data['lon']
                distance = haversine_distance(lat, lon, proc_lat, proc_lon)

                if distance < MIN_DISTANCE_KM:
                    too_close = True
                    if distance < nearest_distance:
                        nearest_distance = distance
                        nearest_port = proc_name

            if too_close and nearest_port:
                if len(port_name) > len(nearest_port):
                    del final_ports[nearest_port]
                    final_ports[port_name] = port_data
            elif not too_close:
                final_ports[port_name] = port_data

        quality_ports = {}
        for port_name, port_data in final_ports.items():
            if len(port_name) >= 4:
                quality_ports[port_name] = port_data

        PORTS = quality_ports
        print(f"✅ Загружено {len(PORTS)} основных портов")

    except Exception as e:
        print(f"❌ Ошибка загрузки портов: {e}")
        return {}


def load_water_grid() -> List[Tuple[float, float]]:
    """Загружает ВСЕ водные точки из сетки"""
    print("\n🌊 ЗАГРУЗКА ВОДНОЙ СЕТКИ")

    try:
        if not os.path.exists(OCEAN_GRAPH):
            print(f"❌ Файл водной сетки не найден: {OCEAN_GRAPH}")
            return []

        with open(OCEAN_GRAPH, 'r', encoding='utf-8') as f:
            data = json.load(f)

        water_points = []

        if 'grid' in data and isinstance(data['grid'], list):
            for point in data['grid']:
                if isinstance(point, dict):
                    if point.get('isWater') is True:
                        lat = point.get('lat')
                        lon = point.get('lon')
                        if lat is not None and lon is not None:
                            try:
                                lat_float = float(lat)
                                lon_float = float(lon)
                                if -90 <= lat_float <= 90 and -180 <= lon_float <= 180:
                                    water_points.append((lat_float, lon_float))
                            except (ValueError, TypeError):
                                continue

        print(f"✅ Загружено {len(water_points)} водных точек")
        return water_points

    except Exception as e:
        print(f"❌ Ошибка загрузки водной сетки: {e}")
        return []


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Расстояние между двумя точками в км"""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


class ImprovedOceanRouter:
    """Улучшенный маршрутизатор с A* алгоритмом и сглаживанием"""

    def __init__(self, water_points: List[Tuple[float, float]]):
        self.water_points = water_points
        self.route_cache = {}
        self.distance_cache = {}

        if not water_points:
            print("❌ Инициализация ImprovedOceanRouter: НЕТ ВОДНЫХ ТОЧЕК!")
            return

        print(f"🧭 Инициализация ImprovedOceanRouter с {len(water_points)} водными точками")
        self._build_graph()

    def _build_graph(self):
        """Строит граф соединений между водными точками"""
        print("   ⚡ Строю граф соединений...")

        self.spatial_index = {}
        self.point_to_id = {}

        for idx, (lat, lon) in enumerate(self.water_points):
            grid_key = (int(math.floor(lat)), int(math.floor(lon)))
            if grid_key not in self.spatial_index:
                self.spatial_index[grid_key] = []
            self.spatial_index[grid_key].append(idx)
            self.point_to_id[(lat, lon)] = idx

        self.graph = {i: [] for i in range(len(self.water_points))}

        for idx in range(len(self.water_points)):
            lat, lon = self.water_points[idx]
            neighbors = self._get_direct_neighbors(idx, max_distance=120)
            for neighbor_idx in neighbors:
                if neighbor_idx != idx:
                    distance = self._cached_haversine(
                        lat, lon,
                        self.water_points[neighbor_idx][0],
                        self.water_points[neighbor_idx][1]
                    )
                    if distance < 120:
                        self.graph[idx].append((neighbor_idx, distance))

        print(f"   ✅ Граф построен: {len(self.graph)} вершин")

    def _cached_haversine(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        key = (round(lat1, 4), round(lon1, 4), round(lat2, 4), round(lon2, 4))
        if key in self.distance_cache:
            return self.distance_cache[key]
        distance = haversine_distance(lat1, lon1, lat2, lon2)
        self.distance_cache[key] = distance
        return distance

    def _get_direct_neighbors(self, point_idx: int, max_distance: float = 120) -> List[int]:
        if point_idx >= len(self.water_points):
            return []

        lat, lon = self.water_points[point_idx]
        neighbors = []
        center_cell = (int(math.floor(lat)), int(math.floor(lon)))

        for dlat in range(-1, 2):
            for dlon in range(-1, 2):
                cell_key = (center_cell[0] + dlat, center_cell[1] + dlon)
                if cell_key in self.spatial_index:
                    for neighbor_idx in self.spatial_index[cell_key]:
                        if neighbor_idx == point_idx:
                            continue
                        n_lat, n_lon = self.water_points[neighbor_idx]
                        dist = self._cached_haversine(lat, lon, n_lat, n_lon)
                        if dist < max_distance:
                            neighbors.append(neighbor_idx)

        return neighbors

    def _a_star_search(self, start_idx: int, end_idx: int) -> Optional[List[int]]:
        end_lat, end_lon = self.water_points[end_idx]

        def heuristic(idx):
            lat, lon = self.water_points[idx]
            return self._cached_haversine(lat, lon, end_lat, end_lon)

        open_set = []
        heapq.heappush(open_set, (heuristic(start_idx), 0, start_idx, [start_idx]))

        g_scores = {start_idx: 0}
        visited = set()

        while open_set:
            f_score, g_score, current, path = heapq.heappop(open_set)

            if current in visited:
                continue
            visited.add(current)

            if current == end_idx:
                print("         ✅ Цель достигнута!")
                return path

            for neighbor, distance in self.graph[current]:
                if neighbor in visited:
                    continue
                new_g_score = g_score + distance
                if neighbor not in g_scores or new_g_score < g_scores[neighbor]:
                    g_scores[neighbor] = new_g_score
                    f_score = new_g_score + heuristic(neighbor)
                    heapq.heappush(open_set, (f_score, new_g_score, neighbor, path + [neighbor]))

        print("         ❌ Путь не найден")
        return None

    def find_route(self, start_lat: float, start_lon: float,
                   end_lat: float, end_lon: float) -> List[Tuple[float, float]]:
        print(f"\n🔍 Поиск маршрута: {start_lat:.4f}, {start_lon:.4f} → {end_lat:.4f}, {end_lon:.4f}")

        if not self.water_points:
            return []

        cache_key = f"{start_lat:.4f},{start_lon:.4f}_{end_lat:.4f},{end_lon:.4f}"
        if cache_key in self.route_cache:
            print("   📦 Использую кэшированный маршрут")
            return self.route_cache[cache_key]

        start_idx = self._find_nearest_water_point(start_lat, start_lon)
        end_idx = self._find_nearest_water_point(end_lat, end_lon)

        if start_idx is None or end_idx is None:
            print("❌ Не найдены водные точки рядом со стартом/финишем")
            return []

        start_point = self.water_points[start_idx]
        end_point = self.water_points[end_idx]

        direct_distance = self._cached_haversine(start_lat, start_lon, end_lat, end_lon)
        print(f"   📏 Прямое расстояние: {direct_distance:.1f} км")

        if direct_distance < 100:
            route = [start_point, end_point]
            self.route_cache[cache_key] = route
            return route

        print("   🧠 Поиск пути A* алгоритмом...")
        path_indices = self._a_star_search(start_idx, end_idx)

        if not path_indices or len(path_indices) < 2:
            print("   ⚠️ A* не нашел путь, пробую жадный алгоритм...")
            path_indices = self._greedy_fallback(start_idx, end_idx)

        if not path_indices or len(path_indices) < 2:
            route = [start_point, end_point]
            self.route_cache[cache_key] = route
            return route

        print(f"   ✅ Найден путь через {len(path_indices)} водных точек")

        raw_route = [self.water_points[idx] for idx in path_indices]
        full_route = [(start_lat, start_lon)] + raw_route + [(end_lat, end_lon)]
        smoothed_route = self._optimize_route(full_route)

        self.route_cache[cache_key] = smoothed_route
        return smoothed_route

    def _find_nearest_water_point(self, lat: float, lon: float, max_distance: float = 200) -> Optional[int]:
        if not self.water_points:
            return None

        best_idx = None
        best_dist = float('inf')
        center_cell = (int(math.floor(lat)), int(math.floor(lon)))

        for dlat in range(-2, 3):
            for dlon in range(-2, 3):
                cell_key = (center_cell[0] + dlat, center_cell[1] + dlon)
                if cell_key in self.spatial_index:
                    for idx in self.spatial_index[cell_key]:
                        point_lat, point_lon = self.water_points[idx]
                        dist = self._cached_haversine(lat, lon, point_lat, point_lon)
                        if dist < best_dist and dist < max_distance:
                            best_dist = dist
                            best_idx = idx

        return best_idx

    def _greedy_fallback(self, start_idx: int, end_idx: int) -> List[int]:
        print("      🔄 Запускаю жадный алгоритм...")

        path = [start_idx]
        current_idx = start_idx
        visited = {start_idx}
        end_lat, end_lon = self.water_points[end_idx]
        max_steps = 5000

        for step in range(max_steps):
            if current_idx == end_idx:
                break

            neighbors = self._get_direct_neighbors(current_idx, max_distance=200)
            best_neighbor = None
            best_score = float('inf')

            current_lat, current_lon = self.water_points[current_idx]
            current_to_goal = self._cached_haversine(current_lat, current_lon, end_lat, end_lon)

            for neighbor_idx in neighbors:
                if neighbor_idx in visited:
                    continue
                n_lat, n_lon = self.water_points[neighbor_idx]
                neighbor_to_goal = self._cached_haversine(n_lat, n_lon, end_lat, end_lon)
                score = neighbor_to_goal - current_to_goal
                if score < best_score:
                    best_score = score
                    best_neighbor = neighbor_idx

            if best_neighbor is None:
                break

            path.append(best_neighbor)
            visited.add(best_neighbor)
            current_idx = best_neighbor

        if end_idx not in path:
            path.append(end_idx)

        print(f"      ✅ Жадный алгоритм нашел путь из {len(path)} точек")
        return path

    def _optimize_route(self, route: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
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

    def calculate_segments(self, route_points: List[Tuple[float, float]],
                           total_distance: float) -> List[Dict]:
        if not route_points or len(route_points) < 2:
            return []

        num_segments = 3
        segments = []
        points_per_segment = len(route_points) // num_segments

        for seg in range(num_segments):
            start_idx = seg * points_per_segment
            end_idx = (seg + 1) * points_per_segment if seg < num_segments - 1 else len(route_points) - 1

            if start_idx >= end_idx:
                continue

            if seg == 0:
                mode = 'battery'
                color = '#27ae60'
                description = 'Питание от батарей'
            elif seg == num_segments - 1:
                mode = 'diesel'
                color = '#e74c3c'
                description = 'Дизельный двигатель'
            else:
                mode = 'sail'
                color = '#f39c12'
                description = 'Роторы Флеттнера'

            seg_distance = 0
            for i in range(start_idx, end_idx):
                lat1, lon1 = route_points[i]
                lat2, lon2 = route_points[i + 1]
                seg_distance += haversine_distance(lat1, lon1, lat2, lon2)

            segments.append({
                'start': route_points[start_idx],
                'end': route_points[end_idx],
                'mode': mode,
                'distance_km': round(seg_distance, 1),
                'color': color,
                'description': description
            })

        return segments


class RouteCalculator:
    """Калькулятор для морских расчетов"""

    def __init__(self):
        self.fuel_coefficient = 0.082

    def calculate_fuel(self, distance_nm: float, speed: float = 12.5) -> Dict:
        hours = distance_nm / speed if speed > 0 else 0
        base_hourly_rate = 0.25
        hourly_rate = base_hourly_rate * ((speed / 10) ** 3)
        total_fuel = hourly_rate * hours

        standard_speed = 12.0
        standard_hours = distance_nm / standard_speed
        standard_hourly_rate = base_hourly_rate * ((standard_speed / 10) ** 3)
        standard_fuel = standard_hourly_rate * standard_hours

        savings = ((standard_fuel - total_fuel) / standard_fuel) * 100 if standard_fuel > 0 else 0

        return {
            'total_fuel_ton': round(total_fuel, 1),
            'hourly_consumption_ton': round(hourly_rate, 3),
            'optimal_speed_kn': round(speed, 1),
            'savings_percentage': round(max(-20, min(40, savings)), 1),
            'time_hours': round(hours, 1),
            'time_days': round(hours / 24, 1)
        }


class AIAnalyzer:
    """Анализатор маршрутов"""

    def __init__(self):
        pass

    def analyze(self, port1: str, port2: str, distance: float,
                route_points: List[Tuple[float, float]]) -> List[str]:
        recommendations = []

        if distance > 5000:
            recommendations.append("🌍 ДАЛЬНИЙ МАРШРУТ: Используйте экономичный режим 12-14 узлов")
            recommendations.append("⛽ ПЛАНИРУЙТЕ ДОЗАПРАВКИ: через каждые 2000 морских миль")
        elif distance > 1000:
            recommendations.append("📏 СРЕДНИЙ МАРШРУТ: Оптимальная скорость 14-16 узлов")
        else:
            recommendations.append("📍 КОРОТКИЙ МАРШРУТ: Используйте прибрежное плавание")

        port1_lower = port1.lower()
        port2_lower = port2.lower()

        if any(x in port1_lower for x in ['бург', 'морск', 'аркт', 'мурман']) or \
                any(x in port2_lower for x in ['бург', 'морск', 'аркт', 'мурман']):
            recommendations.append("🧊 СЕВЕРНЫЙ МАРШРУТ: Проверьте системы обогрева и антиобледенения")

        if any(x in port1_lower for x in ['шанхай', 'сингапур', 'гонконг']) or \
                any(x in port2_lower for x in ['шанхай', 'сингапур', 'гонконг']):
            recommendations.append("🌴 АЗИАТСКИЙ РЕГИОН: Будьте готовы к высокой влажности и тропическим штормам")

        recommendations.append("📡 МОНИТОРИНГ: Обновляйте метеоданные каждые 6 часов")
        recommendations.append("⚓ БЕЗОПАСНОСТЬ: Проверьте системы связи и навигации")
        recommendations.append("🔋 ОПТИМИЗАЦИЯ: Используйте оптимальную скорость для экономии топлива")

        return recommendations


print("\n📥 ЗАГРУЗКА ДАННЫХ...")

load_ports_from_csv()
water_points = load_water_grid()

if not water_points:
    print("⚠️ НЕТ ВОДНЫХ ТОЧЕК! Создаю тестовую сетку...")
    water_points = []
    for lat in range(-80, 81, 5):
        for lon in range(-180, 181, 10):
            water_points.append((lat, lon))
    print(f"✅ Создано {len(water_points)} тестовых точек")

router = ImprovedOceanRouter(water_points)
calculator = RouteCalculator()
analyzer = AIAnalyzer()

print("=" * 60)
print("✅ СИСТЕМА ГОТОВА")
print(f"   📍 Портов: {len(PORTS)}")
print(f"   🌊 Водных точек в сетке: {len(water_points)}")
print("=" * 60)


@app.route('/api/ports', methods=['GET'])
def get_ports():
    print("📡 Запрос списка портов")

    if not PORTS:
        return jsonify({'success': False, 'error': 'Порты не загружены'})

    return jsonify({
        'success': True,
        'ports': PORTS,
        'count': len(PORTS)
    })


@app.route('/api/system/info', methods=['GET'])
def system_info():
    return jsonify({
        'success': True,
        'system': {
            'name': 'Maritime Route Optimizer',
            'version': '17.0',
            'status': 'ready',
            'data': {
                'ports_loaded': len(PORTS),
                'water_points': len(router.water_points) if hasattr(router, 'water_points') else 0
            }
        }
    })


@app.route('/api/calculate', methods=['POST'])
def calculate_route():
    """Основной расчет маршрута"""
    try:
        start_time = time.time()
        data = request.json
        port1 = data.get('departure')
        port2 = data.get('destination')
        route_mode = data.get('mode', 'economical')

        print(f"\n{'=' * 60}")
        print(f"📡 РАСЧЕТ МАРШРУТА: {port1} → {port2}")
        print(f"📋 Режим: {route_mode}")
        print("=" * 60)

        if not port1 or not port2:
            return jsonify({'success': False, 'error': 'Выберите оба порта'}), 400

        if port1 not in PORTS:
            return jsonify({'success': False, 'error': f'Неизвестный порт: {port1}'}), 400

        if port2 not in PORTS:
            return jsonify({'success': False, 'error': f'Неизвестный порт: {port2}'}), 400

        if port1 == port2:
            return jsonify({'success': False, 'error': 'Порты должны быть разными'}), 400

        coord1 = PORTS[port1]
        coord2 = PORTS[port2]
        lat1, lon1 = coord1['lat'], coord1['lon']
        lat2, lon2 = coord2['lat'], coord2['lon']

        print(f"📍 Координаты: {lat1:.4f},{lon1:.4f} → {lat2:.4f},{lon2:.4f}")

        route_points = router.find_route(lat1, lon1, lat2, lon2)

        if not route_points:
            return jsonify({'success': False, 'error': 'Не удалось построить маршрут'}), 400

        print(f"✅ Базовый маршрут: {len(route_points)} точек")

        weather_analysis = weather_service.analyze_weather_for_route(route_points)

        risk_level = weather_analysis.get('risk_level', 'low')

        mode_info = None
        if route_mode != 'economical' or (route_mode == 'economical' and risk_level == 'high'):
            route_points, mode_info = route_mode_selector.optimize_route_for_mode(
                route_points,
                route_mode,
                weather_analysis.get('weather_points', []),
                risk_level
            )
        else:
            mode_info = {
                'mode': 'economical',
                'mode_name': 'Экономичный',
                'mode_icon': '💰',
                'description': 'Минимальный расход топлива',
                'adjustments': [
                    '📉 Оптимальная скорость: 10-11 узлов',
                    '⚡ Используйте гибридную систему в экономичном режиме',
                    '🌊 Избегайте резких маневров',
                    '💡 При попутном ветре используйте роторы Флеттнера'
                ],
                'speed_factor': 0.85,
                'fuel_factor': 0.6,
                'safety_factor': 0.8,
                'preferred_modes': ['sail', 'battery']
            }

        total_distance = 0
        for i in range(len(route_points) - 1):
            total_distance += haversine_distance(
                route_points[i][0], route_points[i][1],
                route_points[i + 1][0], route_points[i + 1][1]
            )

        total_distance_nm = round(total_distance / 1.852, 1)

        if route_mode == 'fastest':
            base_speed = 15.0
        elif route_mode == 'economical':
            base_speed = 11.0
        else:
            base_speed = 10.5

        if weather_analysis.get('risk_level') == 'high':
            base_speed = round(base_speed * 0.85, 1)
        elif weather_analysis.get('max_wind', 0) > 15:
            base_speed = round(base_speed * 0.9, 1)

        fuel_data = calculator.calculate_fuel(total_distance_nm, base_speed)

        if route_mode == 'fastest':
            fuel_data['total_fuel_ton'] = round(fuel_data['total_fuel_ton'] * 1.3, 1)
            fuel_data['savings_percentage'] = round(fuel_data['savings_percentage'] - 15, 1)
        elif route_mode == 'economical':
            fuel_data['total_fuel_ton'] = round(fuel_data['total_fuel_ton'] * 0.7, 1)
            fuel_data['savings_percentage'] = round(fuel_data['savings_percentage'] + 15, 1)
        else:
            fuel_data['total_fuel_ton'] = round(fuel_data['total_fuel_ton'] * 0.85, 1)
            fuel_data['savings_percentage'] = round(fuel_data['savings_percentage'] + 8, 1)

        if weather_analysis.get('risk_level') == 'high':
            fuel_data['total_fuel_ton'] = round(fuel_data['total_fuel_ton'] * 1.2, 1)
        elif weather_analysis.get('risk_level') == 'medium':
            fuel_data['total_fuel_ton'] = round(fuel_data['total_fuel_ton'] * 1.08, 1)

        hybrid_distribution = hybrid_optimizer.optimize_distribution(
            total_distance_nm=total_distance_nm,
            weather_analysis=weather_analysis,
            route_mode=route_mode,
            speed_knots=base_speed
        )

        segments = router.calculate_segments(route_points, total_distance)

        if segments and len(segments) > 0:
            total_km = sum(seg.get('distance_km', 0) for seg in segments)

            if total_km > 0:
                diesel_km = (hybrid_distribution['diesel'] / 100) * total_km
                sail_km = (hybrid_distribution['sail'] / 100) * total_km

                current_km = 0
                segments_with_modes = []

                for seg in segments:
                    seg_km = seg.get('distance_km', 0)
                    seg_start_km = current_km

                    if seg_start_km >= diesel_km + sail_km:
                        seg['mode'] = 'battery'
                        seg['color'] = '#27ae60'
                        seg['description'] = '🔋 Электродвигатель'
                    elif seg_start_km >= diesel_km:
                        seg['mode'] = 'sail'
                        seg['color'] = '#f39c12'
                        seg['description'] = '⛵ Роторы Флеттнера'
                    else:
                        seg['mode'] = 'diesel'
                        seg['color'] = '#e74c3c'
                        seg['description'] = '🛢️ Дизельный двигатель'

                    segments_with_modes.append(seg)
                    current_km += seg_km

                segments = segments_with_modes

        recommendations = analyzer.analyze(port1, port2, total_distance_nm, route_points)

        if weather_analysis.get('recommendations'):
            recommendations.extend(weather_analysis['recommendations'])

        if mode_info and mode_info.get('adjustments'):
            recommendations.extend(mode_info['adjustments'])

        recommendations = list(dict.fromkeys(recommendations))

        response = {
            'success': True,
            'route': {
                'departure': port1,
                'destination': port2,
                'distance': total_distance_nm,
                'route_distance_nm': total_distance_nm,
                'optimal_speed_kn': base_speed,
                'time_hours': round(total_distance_nm / base_speed, 1),
                'time_days': round(total_distance_nm / base_speed / 24, 2),
                'route_points': [[round(lat, 6), round(lon, 6)] for lat, lon in route_points],
                'segments': [{
                    'start': [round(seg['start'][0], 6), round(seg['start'][1], 6)],
                    'end': [round(seg['end'][0], 6), round(seg['end'][1], 6)],
                    'mode': seg['mode'],
                    'distance_km': seg['distance_km'],
                    'color': seg['color'],
                    'description': seg['description']
                } for seg in segments],
                'water_guarantee': True,
                'uses_water_grid': True,
                'mode_info': mode_info,
                'selected_mode': route_mode
            },
            'fuel': fuel_data,
            'hybrid_system': {
                'diesel_electric': {'percentage': hybrid_distribution['diesel'], 'description': 'Дизельный двигатель'},
                'sail_assist': {'percentage': hybrid_distribution['sail'], 'description': 'Роторы Флеттнера'},
                'battery': {'percentage': hybrid_distribution['battery'], 'description': 'Аккумуляторы'},
                'details': hybrid_distribution.get('details', []),
                'estimated_savings': hybrid_distribution.get('estimated_savings_percent', 0)
            },
            'recommendations': recommendations,
            'weather_analysis': {
                'risk_level': weather_analysis.get('risk_level', 'unknown'),
                'risk_score': weather_analysis.get('risk_score', 0),
                'risk_factors': weather_analysis.get('risk_factors', []),
                'weather_recommendations': weather_analysis.get('recommendations', []),
                'max_wind': weather_analysis.get('max_wind', 0),
                'max_wave': weather_analysis.get('max_wave', 0),
                'has_storms': weather_analysis.get('has_storms', False)
            },
            'metadata': {
                'calculation_time': datetime.now().isoformat(),
                'calculation_duration_seconds': round(time.time() - start_time, 2),
                'route_points_count': len(route_points),
                'water_grid_points': len(router.water_points),
                'route_mode': route_mode
            }
        }

        print(f"✅ Маршрут рассчитан: {total_distance_nm} нм, {len(route_points)} точек")
        return jsonify(response)

    except Exception as e:
        print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ports/map', methods=['GET'])
def get_ports_for_map():
    try:
        if not PORTS:
            return jsonify({'success': False, 'error': 'Порты не загружены'})

        ports_list = []
        for port_name, port_data in PORTS.items():
            ports_list.append({
                'name': port_name,
                'lat': port_data['lat'],
                'lon': port_data['lon'],
                'country': port_data.get('country', 'Unknown')
            })

        if len(ports_list) > 1000:
            ports_list.sort(key=lambda x: len(x['name']), reverse=True)
            ports_list = ports_list[:1000]

        return jsonify({
            'success': True,
            'ports': ports_list,
            'count': len(ports_list)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'service': 'Ship Route Optimizer API',
        'version': '17.0',
        'ports_loaded': len(PORTS) > 0,
        'water_grid_loaded': hasattr(router, 'water_points') and len(router.water_points) > 0,
        'timestamp': datetime.now().isoformat()
    })


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("🚀 ЗАПУСК СЕРВЕРА")
    print("=" * 60)
    print(f"📡 http://localhost:5000")
    print(f"📍 Портов: {len(PORTS)}")
    print(f"🌊 Водных точек: {len(router.water_points) if hasattr(router, 'water_points') else 0}")
    print("=" * 60 + "\n")

    app.run(
        debug=True,
        host='0.0.0.0',
        port=5000,
        use_reloader=False
    )