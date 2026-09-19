import requests
import os
from datetime import datetime
from typing import Dict, List, Tuple


class WeatherService:
    """Сервис для получения погодных данных в реальном времени"""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv('OPENWEATHER_API_KEY', 'DEMO_KEY')
        self.base_url = "https://api.openweathermap.org/data/2.5"
        self.cache = {}
        self.cache_duration = 3600

    def get_weather_at_point(self, lat: float, lon: float) -> Dict:
        """Получение погоды в конкретной точке"""
        cache_key = f"{round(lat, 2)}_{round(lon, 2)}"

        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if (datetime.now() - timestamp).seconds < self.cache_duration:
                return cached_data

        try:
            if self.api_key == 'DEMO_KEY':
                weather = self._generate_demo_weather(lat, lon)
            else:
                url = f"{self.base_url}/weather"
                params = {
                    'lat': lat,
                    'lon': lon,
                    'appid': self.api_key,
                    'units': 'metric',
                    'lang': 'ru'
                }
                response = requests.get(url, params=params, timeout=10)

                if response.status_code == 200:
                    data = response.json()
                    weather = {
                        'wind_speed': data['wind']['speed'],
                        'wind_direction': data['wind'].get('deg', 0),
                        'wave_height': self._estimate_wave_height(data['wind']['speed']),
                        'air_temperature': data['main']['temp'],
                        'sea_temperature': self._estimate_sea_temp(data['main']['temp'], lat),
                        'pressure': data['main']['pressure'],
                        'humidity': data['main']['humidity'],
                        'weather_condition': data['weather'][0]['description'],
                        'weather_main': data['weather'][0]['main'],
                        'visibility': data.get('visibility', 10000),
                        'clouds': data.get('clouds', {}).get('all', 0)
                    }
                else:
                    weather = self._generate_demo_weather(lat, lon)

            self.cache[cache_key] = (weather, datetime.now())
            return weather

        except Exception as e:
            print(f"⚠️ Ошибка получения погоды: {e}")
            return self._generate_demo_weather(lat, lon)

    def get_weather_along_route(self, route_points: List[Tuple[float, float]],
                                num_samples: int = 10) -> List[Dict]:
        """Получение погоды вдоль маршрута"""
        if len(route_points) < 2:
            return []

        weather_data = []
        step = max(1, len(route_points) // num_samples)

        for i in range(0, len(route_points), step):
            lat, lon = route_points[i]
            weather = self.get_weather_at_point(lat, lon)
            weather['point_index'] = i
            weather['lat'] = lat
            weather['lon'] = lon
            weather_data.append(weather)

        return weather_data

    def analyze_weather_for_route(self, route_points: List[Tuple[float, float]]) -> Dict:
        """Анализ погодных условий для маршрута"""
        weather_points = self.get_weather_along_route(route_points)

        if not weather_points:
            return {'warning': 'Нет данных о погоде', 'risk_level': 'unknown'}

        high_wind = []
        high_waves = []
        storms = []
        low_visibility = []

        for wp in weather_points:
            if wp.get('wind_speed', 0) > 15:
                high_wind.append(wp)
            if wp.get('wave_height', 0) > 3:
                high_waves.append(wp)
            if wp.get('weather_main') in ['Thunderstorm', 'Storm', 'Squall']:
                storms.append(wp)
            if wp.get('visibility', 10000) < 2000:
                low_visibility.append(wp)

        risk_score = 0
        risk_factors = []

        if high_wind:
            risk_score += 30
            risk_factors.append(
                f"💨 Сильный ветер ({len(high_wind)} участков, до {max(w['wind_speed'] for w in high_wind):.1f} м/с)")

        if high_waves:
            risk_score += 35
            risk_factors.append(
                f"🌊 Высокие волны ({len(high_waves)} участков, до {max(w['wave_height'] for w in high_waves):.1f} м)")

        if storms:
            risk_score += 40
            risk_factors.append(f"⛈️ Штормовые условия ({len(storms)} участков)")

        if low_visibility:
            risk_score += 20
            risk_factors.append(f"🌫️ Плохая видимость ({len(low_visibility)} участков)")

        recommendations = []
        if risk_score > 50:
            recommendations.append("⚠️ ВЫСОКИЙ УРОВЕНЬ РИСКА: Рекомендуется изменить маршрут или отложить плавание")
            recommendations.append("📡 Увеличьте частоту обновления погодных данных до 1 часа")
        elif risk_score > 25:
            recommendations.append("⚡ СРЕДНИЙ УРОВЕНЬ РИСКА: Будьте внимательны на отдельных участках")

        if high_wind:
            recommendations.append(
                "💡 При ветре >15 м/с используйте режим экономии топлива (снизьте скорость до 10 узлов)")
        if high_waves:
            recommendations.append("💡 При высоких волнах увеличьте скорость на 10% для лучшей стабильности")

        if not recommendations:
            recommendations.append("✅ Погодные условия благоприятные для плавания")

        return {
            'risk_level': 'high' if risk_score > 50 else ('medium' if risk_score > 25 else 'low'),
            'risk_score': risk_score,
            'risk_factors': risk_factors,
            'recommendations': recommendations,
            'weather_points': weather_points,
            'max_wind': max([w.get('wind_speed', 0) for w in weather_points]),
            'max_wave': max([w.get('wave_height', 0) for w in weather_points]),
            'has_storms': len(storms) > 0
        }

    def _estimate_wave_height(self, wind_speed: float) -> float:
        return round(0.3 * wind_speed ** 0.8, 1)

    def _estimate_sea_temp(self, air_temp: float, lat: float) -> float:
        base_temp = air_temp - 2
        lat_factor = abs(lat) / 90 * 15
        return round(base_temp - lat_factor, 1)

    def _generate_demo_weather(self, lat: float, lon: float) -> Dict:
        import random
        random.seed(hash(f"{round(lat, 1)}_{round(lon, 1)}") % 2 ** 32)

        is_north = lat > 30
        is_tropical = abs(lat) < 23.5
        is_pacific = 120 < lon < 240 or (lon > 120 and lon < 180) or (lon < -120 and lon > -180)

        if is_tropical:
            wind_base = random.uniform(3, 12)
            temp_base = random.uniform(22, 32)
            condition = random.choice(['Clear', 'Clouds', 'Rain'])
        elif is_north:
            wind_base = random.uniform(5, 18)
            temp_base = random.uniform(-5, 15)
            condition = random.choice(['Clouds', 'Rain', 'Snow'])
        else:
            wind_base = random.uniform(4, 15)
            temp_base = random.uniform(10, 25)
            condition = random.choice(['Clear', 'Clouds', 'Rain'])

        if -60 < lon < -20 and lat > 20:
            wind_base *= 1.5

        if is_pacific:
            wind_base *= 1.3

        return {
            'wind_speed': round(min(25, wind_base), 1),
            'wind_direction': random.randint(0, 359),
            'wave_height': round(self._estimate_wave_height(wind_base), 1),
            'air_temperature': round(temp_base, 1),
            'sea_temperature': round(temp_base - (2 if is_north else 0), 1),
            'pressure': random.randint(990, 1030),
            'humidity': random.randint(60, 95),
            'weather_condition': condition,
            'weather_main': condition,
            'visibility': random.randint(2000, 15000),
            'clouds': random.randint(10, 100)
        }


weather_service = WeatherService()


def get_weather_recommendations(route_points: List[Tuple[float, float]]) -> Dict:
    return weather_service.analyze_weather_for_route(route_points)