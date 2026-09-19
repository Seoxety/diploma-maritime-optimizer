from typing import Dict


class HybridSystemOptimizer:
    """Динамическая гибридная система: дизель / паруса / батареи"""

    def __init__(self):
        self.battery_capacity_kwh = 5000
        self.battery_charge_rate = 500
        self.sail_efficiency_wind = 0.15

    def optimize_distribution(self,
                              total_distance_nm: float,
                              weather_analysis: Dict,
                              route_mode: str,
                              speed_knots: float) -> Dict:

        if total_distance_nm < 500:
            base = {'diesel': 25, 'sail': 20, 'battery': 55}
        elif total_distance_nm < 1500:
            base = {'diesel': 30, 'sail': 35, 'battery': 35}
        elif total_distance_nm < 4000:
            base = {'diesel': 35, 'sail': 45, 'battery': 20}
        else:
            base = {'diesel': 40, 'sail': 50, 'battery': 10}

        weather_factors = self._calculate_weather_factors(weather_analysis)
        mode_factors = self._calculate_mode_factors(route_mode)

        final = {}
        details = []

        for mode in ['diesel', 'sail', 'battery']:
            value = base[mode]
            value += weather_factors.get(mode, 0)
            value += mode_factors.get(mode, 0)

            if mode == 'sail' and value < 15:
                value = 15
                details.append("⛵ Минимальное использование парусов: 15%")
            if mode == 'battery' and value < 10:
                value = 10
                details.append("🔋 Минимальное использование батарей: 10%")
            if mode == 'diesel' and value < 20:
                value = 20
                details.append("🛢️ Минимальное использование дизеля: 20%")

            value = max(5, min(75, value))
            final[mode] = round(value)

        total = sum(final.values())
        if total != 100:
            diff = 100 - total
            if route_mode == 'economical' and weather_analysis.get('max_wind', 0) > 8:
                final['sail'] += diff
                details.append(f"🌬️ Экономичный режим + попутный ветер (+{diff}% к парусам)")
            elif route_mode == 'fastest':
                final['diesel'] += diff
                details.append(f"⚡ Быстрый режим (+{diff}% к дизелю)")
            elif route_mode == 'safe':
                final['battery'] += diff
                details.append(f"🛡️ Безопасный режим (+{diff}% к батареям)")
            else:
                final['sail'] += diff
                details.append(f"💰 Оптимизация (+{diff}% к парусам)")

        total = sum(final.values())
        if total != 100:
            factor = 100 / total
            for mode in final:
                final[mode] = round(final[mode] * factor)

        if final['sail'] > 35:
            details.append(f"⛵ Активное использование роторов Флеттнера ({final['sail']}%)")
            if weather_analysis.get('max_wind', 0) > 10:
                details.append(f"🌬️ Отличные условия для парусов (ветер {weather_analysis['max_wind']:.1f} м/с)")
        elif final['battery'] > 30:
            details.append(f"🔋 Интенсивное использование батарей ({final['battery']}%)")
        else:
            details.append(f"🛢️ Дизель - основной режим ({final['diesel']}%)")

        estimated_savings = self._calculate_savings(final, weather_analysis, total_distance_nm, speed_knots)

        print(f"   ИТОГОВОЕ РАСПРЕДЕЛЕНИЕ: Д={final['diesel']}% П={final['sail']}% Б={final['battery']}%")

        return {
            'diesel': final['diesel'],
            'sail': final['sail'],
            'battery': final['battery'],
            'details': details,
            'estimated_savings_percent': estimated_savings,
            'weather_impact': self._get_weather_impact_description(weather_analysis)
        }

    def _calculate_mode_factors(self, route_mode: str) -> Dict:
        factors = {'diesel': 0, 'sail': 0, 'battery': 0}

        if route_mode == 'fastest':
            factors['diesel'] = 25
            factors['sail'] = -15
            factors['battery'] = -10
        elif route_mode == 'economical':
            factors['diesel'] = -20
            factors['sail'] = 25
            factors['battery'] = -5
        elif route_mode == 'safe':
            factors['diesel'] = -10
            factors['sail'] = -10
            factors['battery'] = 20

        return factors

    def _calculate_weather_factors(self, weather_analysis: Dict) -> Dict:
        factors = {'diesel': 0, 'sail': 0, 'battery': 0}

        wind_speed = weather_analysis.get('max_wind', 0)
        wave_height = weather_analysis.get('max_wave', 0)
        risk_level = weather_analysis.get('risk_level', 'low')

        if wind_speed > 15:
            factors['sail'] = 25
            factors['diesel'] = -15
            factors['battery'] = -10
        elif wind_speed > 8:
            factors['sail'] = 15
            factors['diesel'] = -10
            factors['battery'] = -5
        elif wind_speed > 5:
            factors['sail'] = 8
            factors['diesel'] = -5
            factors['battery'] = -3
        elif wind_speed < 3:
            factors['sail'] = -15
            factors['diesel'] = 10
            factors['battery'] = 5

        if wave_height > 3:
            factors['diesel'] = 10
            factors['sail'] = -10
        elif wave_height > 2:
            factors['diesel'] = 5
            factors['sail'] = -5

        if risk_level == 'high':
            factors['diesel'] = 15
            factors['sail'] = -20
            factors['battery'] = 5
        elif risk_level == 'medium':
            factors['diesel'] = 8
            factors['sail'] = -10
            factors['battery'] = 2

        return factors

    def _calculate_savings(self, distribution: Dict, weather_analysis: Dict,
                           distance_nm: float, speed_knots: float) -> int:
        consumption_factors = {
            'diesel': 1.0,
            'sail': 0.20,
            'battery': 0.05
        }

        weighted_factor = (
                                  distribution['diesel'] * consumption_factors['diesel'] +
                                  distribution['sail'] * consumption_factors['sail'] +
                                  distribution['battery'] * consumption_factors['battery']
                          ) / 100

        savings = (1 - weighted_factor) * 100

        wind_speed = weather_analysis.get('max_wind', 0)
        if wind_speed > 12:
            savings += 12
        elif wind_speed > 8:
            savings += 8
        elif wind_speed > 5:
            savings += 4

        savings = max(15, min(65, savings))
        return round(savings)

    def _get_weather_impact_description(self, weather_analysis: Dict) -> str:
        wind = weather_analysis.get('max_wind', 0)
        waves = weather_analysis.get('max_wave', 0)

        if wind > 15:
            return f"🌬️ Сильный ветер ({wind} м/с) - роторы Флеттнера эффективны, снижение расхода до 30%"
        elif wind > 8:
            return f"🌊 Умеренный ветер ({wind} м/с) - благоприятные условия для парусного режима"
        elif waves > 3:
            return f"⚠️ Высокие волны ({waves} м) - повышенный расход топлива"
        else:
            return "✅ Погодные условия благоприятные для экономичного плавания"


hybrid_optimizer = HybridSystemOptimizer()