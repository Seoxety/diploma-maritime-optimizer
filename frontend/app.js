const API_URL = 'http://localhost:5000/api';
let map = null;
let departureMarker = null;
let destinationMarker = null;
let routeLayer = null;
let serverConnected = false;
let portsLoaded = false;

window.onload = async function() {
    await checkServerStatus();
    if (serverConnected) {
        await loadPortsFromAPI();
    }
    setTimeout(initMap, 100);
};

function initMap() {
    const mapElement = document.getElementById('map');
    if (!mapElement) return;

    try {
        if (map) {
            map.remove();
            map = null;
        }

        map = L.map('map', { preferCanvas: true }).setView([50, 30], 3);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors',
            maxZoom: 18,
            minZoom: 2
        }).addTo(map);

        window.addEventListener('resize', function() {
            if (map) setTimeout(() => map.invalidateSize(), 200);
        });

        setTimeout(() => map && map.invalidateSize(), 300);
    } catch (error) {
        console.error('❌ Ошибка инициализации карты:', error);
        setTimeout(initMap, 1000);
    }
}

async function checkServerStatus() {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);

        const response = await fetch(`${API_URL}/health`, {
            method: 'GET',
            headers: { 'Accept': 'application/json' },
            signal: controller.signal
        });

        clearTimeout(timeoutId);

        if (response.ok) {
            serverConnected = true;
            updateServerStatus(true);
            return true;
        }
    } catch (error) {
        serverConnected = false;
        updateServerStatus(false);
    }
    return false;
}

function updateServerStatus(connected) {
    const statusElem = document.getElementById('server-status');
    if (!statusElem) return;
    if (connected) {
        statusElem.innerHTML = 'Сервер: <span class="status-connected">Подключен</span>';
        statusElem.style.background = 'rgba(46, 204, 113, 0.8)';
    } else {
        statusElem.innerHTML = 'Сервер: <span class="status-disconnected">Не подключен</span>';
        statusElem.style.background = 'rgba(231, 76, 60, 0.8)';
    }
}

async function loadPortsFromAPI() {
    if (!serverConnected) return;

    try {
        showLoader('Загрузка портов...');
        const response = await fetch(`${API_URL}/ports`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();

        if (!data.success) {
            showNotification('Ошибка загрузки портов', 'error');
            return;
        }

        const ports = data.ports || {};
        const departureSelect = document.getElementById('departure-port');
        const destinationSelect = document.getElementById('destination-port');

        departureSelect.innerHTML = '<option value="">Выберите порт...</option>';
        destinationSelect.innerHTML = '<option value="">Выберите порт...</option>';

        if (ports && typeof ports === 'object') {
            const sortedNames = Object.keys(ports).sort();

            sortedNames.forEach(portName => {
                const portData = ports[portName];
                const country = portData?.country || 'Unknown';
                const displayName = `${portName} (${country})`;

                departureSelect.add(new Option(displayName, portName));
                destinationSelect.add(new Option(displayName, portName));
            });

            portsLoaded = true;
            showNotification(`Загружено ${sortedNames.length} портов`, 'success');
        }
    } catch (error) {
        console.error('❌ Ошибка загрузки портов:', error);
        showNotification('Ошибка подключения к серверу', 'error');
    } finally {
        hideLoader();
    }
}

async function calculateRoute() {
    const departure = document.getElementById('departure-port').value;
    const destination = document.getElementById('destination-port').value;
    const routeMode = document.getElementById('route-mode')?.value || 'economical';

    if (!departure || !destination) {
        showNotification('Выберите оба порта!', 'error');
        return;
    }

    if (departure === destination) {
        showNotification('Порты должны быть разными!', 'error');
        return;
    }

    showLoader('Рассчитываем маршрут...');

    try {
        const response = await fetch(`${API_URL}/calculate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ departure, destination, mode: routeMode }),
            signal: AbortSignal.timeout(120000)
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();

        if (data.success) {
            updateMapWithRoute(data.route);
            displayResultsFromAPI(data);

            if (data.route?.segments) updateHybridSystemFromSegments(data.route.segments);
            if (data.weather_analysis) displayWeatherInfo(data.weather_analysis);
            if (data.route?.mode_info) displayModeInfo(data.route.mode_info);

            showNotification(`Маршрут ${departure} → ${destination} рассчитан!`, 'success');
        } else {
            showNotification(data.error || 'Ошибка расчета', 'error');
        }
    } catch (error) {
        console.error('Ошибка:', error);
        if (error.name === 'AbortError') {
            showNotification('Расчет слишком долгий. Попробуйте другой маршрут.', 'error');
        } else if (error.message.includes('Failed to fetch')) {
            showNotification('Сервер не запущен. Запустите server.py', 'error');
        } else {
            showNotification('Ошибка при расчете маршрута', 'error');
        }
    } finally {
        hideLoader();
    }
}

function displayWeatherInfo(weatherAnalysis) {
    const weatherInfo = document.getElementById('weather-info');
    const weatherDetails = document.getElementById('weather-details');
    if (!weatherInfo || !weatherDetails) return;

    let riskIcon = '🟢', riskColor = '#27ae60', riskText = 'Низкий';
    if (weatherAnalysis.risk_level === 'medium') {
        riskIcon = '🟡'; riskColor = '#f39c12'; riskText = 'Средний';
    } else if (weatherAnalysis.risk_level === 'high') {
        riskIcon = '🔴'; riskColor = '#e74c3c'; riskText = 'Высокий';
    }

    let weatherHtml = `
        <div style="margin-bottom: 8px;">
            <strong>${riskIcon} Уровень риска:</strong>
            <span style="color: ${riskColor}; font-weight: bold;">${riskText}</span>
            (${weatherAnalysis.risk_score}%)
        </div>
        <div style="margin-bottom: 8px;">
            <strong>💨 Макс. ветер:</strong> ${weatherAnalysis.max_wind || 0} м/с |
            <strong>🌊 Макс. волны:</strong> ${weatherAnalysis.max_wave || 0} м
        </div>
    `;

    if (weatherAnalysis.risk_factors && weatherAnalysis.risk_factors.length > 0) {
        weatherHtml += `<div><strong>⚠️ Факторы риска:</strong><ul style="margin: 5px 0 0 20px;">`;
        weatherAnalysis.risk_factors.forEach(factor => {
            weatherHtml += `<li style="font-size: 11px;">${factor}</li>`;
        });
        weatherHtml += `</ul></div>`;
    }

    if (weatherAnalysis.weather_recommendations && weatherAnalysis.weather_recommendations.length > 0) {
        weatherHtml += `<div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #ddd;">
            <strong>🤖 ИИ-рекомендации:</strong><ul style="margin: 5px 0 0 20px;">`;
        weatherAnalysis.weather_recommendations.forEach(rec => {
            weatherHtml += `<li style="font-size: 11px;">${rec}</li>`;
        });
        weatherHtml += `</ul></div>`;
    }

    weatherDetails.innerHTML = weatherHtml;
    weatherInfo.style.display = 'block';
}

function displayModeInfo(modeInfo) {
    const aiList = document.getElementById('ai-list');
    if (!aiList || !modeInfo.adjustments) return;

    const modeHeader = document.createElement('li');
    modeHeader.style.cssText = 'font-weight: bold; margin-top: 10px; color: #4a69bd;';
    modeHeader.innerHTML = `${modeInfo.mode_icon} РЕЖИМ: ${modeInfo.mode_name}`;
    aiList.insertBefore(modeHeader, aiList.children[1] || null);

    modeInfo.adjustments.forEach(adj => {
        const adjItem = document.createElement('li');
        adjItem.style.cssText = 'font-size: 12px; opacity: 0.9;';
        adjItem.innerHTML = `📌 ${adj}`;
        aiList.insertBefore(adjItem, aiList.children[2] || null);
    });
}
function updateMapWithRoute(routeData) {
    clearMapMarkers();
    if (!map) return;

    if (!routeData.route_points || routeData.route_points.length < 2) {
        showNotification('Ошибка данных маршрута', 'error');
        return;
    }

    const routePoints = routeData.route_points.map(p => [p[0], p[1]]);
    const startPoint = routePoints[0];
    const endPoint = routePoints[routePoints.length - 1];

    departureMarker = L.marker(startPoint, {
        icon: L.divIcon({
            html: '<div style="background:#27ae60;width:24px;height:24px;border-radius:50%;border:3px solid white;box-shadow:0 0 8px rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;color:white;font-weight:bold;font-size:12px;">A</div>',
            iconSize: [24, 24], iconAnchor: [12, 12]
        })
    }).addTo(map).bindPopup(`<b>${routeData.departure}</b><br>Порт отправления`);

    destinationMarker = L.marker(endPoint, {
        icon: L.divIcon({
            html: '<div style="background:#e74c3c;width:24px;height:24px;border-radius:50%;border:3px solid white;box-shadow:0 0 8px rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;color:white;font-weight:bold;font-size:12px;">B</div>',
            iconSize: [24, 24], iconAnchor: [12, 12]
        })
    }).addTo(map).bindPopup(`<b>${routeData.destination}</b><br>Порт назначения`);

    routeLayer = L.layerGroup().addTo(map);

    if (routeData.segments && routeData.segments.length > 0) {
        routeData.segments.forEach(segment => {
            if (segment.start && segment.end) {
                const startIndex = findPointIndex(routePoints, segment.start);
                const endIndex = findPointIndex(routePoints, segment.end);

                if (startIndex !== -1 && endIndex !== -1 && endIndex > startIndex) {
                    const segPoints = routePoints.slice(startIndex, endIndex + 1);
                    L.polyline(segPoints, {
                        color: segment.color || '#3498db',
                        weight: 4, opacity: 0.8,
                        lineCap: 'round', lineJoin: 'round'
                    }).addTo(routeLayer)
                      .bindPopup(`<b>${segment.description}</b><br>Дистанция: ${segment.distance_km} км`);
                } else {
                    L.polyline([segment.start, segment.end], {
                        color: segment.color || '#3498db', weight: 4, opacity: 0.8
                    }).addTo(routeLayer);
                }
            }
        });
    } else {
        L.polyline(routePoints, {
            color: '#3498db', weight: 4, opacity: 0.7,
            lineCap: 'round', lineJoin: 'round'
        }).addTo(routeLayer);
    }

    const bounds = L.latLngBounds(routePoints);
    map.fitBounds(bounds, { padding: [50, 50] });
    setTimeout(() => map.invalidateSize(), 100);
}

function findPointIndex(pointsArray, point) {
    const [targetLat, targetLon] = point;
    for (let i = 0; i < pointsArray.length; i++) {
        const [lat, lon] = pointsArray[i];
        if (Math.abs(lat - targetLat) < 0.0001 && Math.abs(lon - targetLon) < 0.0001) {
            return i;
        }
    }
    return -1;
}

function displayResultsFromAPI(data) {
    const route = data.route;
    const fuel = data.fuel;

    const routeInfo = document.getElementById('route-info');
    if (routeInfo) routeInfo.style.display = 'block';

    if (route && route.departure && route.destination) {
        const routeTitle = document.getElementById('route-title');
        if (routeTitle) routeTitle.textContent = `Маршрут: ${route.departure} → ${route.destination}`;
    }

    const distanceElem = document.getElementById('distance');
    const timeElem = document.getElementById('time');
    const fuelElem = document.getElementById('fuel');
    const savingElem = document.getElementById('saving');

    if (distanceElem) distanceElem.textContent = route?.distance || 0;
    if (timeElem) timeElem.textContent = route?.time_hours || 0;
    if (fuelElem) fuelElem.textContent = fuel?.total_fuel_ton || 0;
    if (savingElem) savingElem.textContent = (fuel?.savings_percentage || 0) + '%';

    const aiList = document.getElementById('ai-list');
    if (aiList) {
        aiList.innerHTML = '';
        const recommendations = data.recommendations || [];

        if (recommendations.length > 0) {
            recommendations.forEach(rec => {
                const li = document.createElement('li');
                li.textContent = rec;
                aiList.appendChild(li);
            });
        } else {
            const li = document.createElement('li');
            li.textContent = 'Рассчитайте маршрут для получения рекомендаций';
            aiList.appendChild(li);
        }
    }
}

function updateHybridSystemFromSegments(segments) {
    const modeBar = document.getElementById('mode-bar');
    if (!modeBar || !segments || segments.length === 0) return;

    modeBar.innerHTML = '';

    const fuelStats = {
        'diesel': { distance: 0, color: '#e74c3c' },
        'sail': { distance: 0, color: '#f39c12' },
        'battery': { distance: 0, color: '#27ae60' }
    };

    let totalDistance = 0;
    segments.forEach(segment => {
        const distance = segment.distance_km || 0;
        totalDistance += distance;
        const fuelType = segment.mode || 'sail';
        if (fuelStats[fuelType]) fuelStats[fuelType].distance += distance;
    });

    if (totalDistance === 0) {
        fuelStats.diesel.distance = 60;
        fuelStats.sail.distance = 30;
        fuelStats.battery.distance = 10;
        totalDistance = 100;
    }

    ['battery', 'sail', 'diesel'].forEach(fuelType => {
        const stats = fuelStats[fuelType];
        const percentage = (stats.distance / totalDistance) * 100;

        const segment = document.createElement('div');
        segment.className = `mode-segment mode-${fuelType}`;
        segment.style.width = `${percentage}%`;
        segment.style.backgroundColor = stats.color;
        segment.textContent = `${percentage.toFixed(0)}%`;
        modeBar.appendChild(segment);
    });
}

async function toggleAllPorts() {
    if (!serverConnected) {
        showNotification('Сначала запустите сервер', 'error');
        return;
    }

    if (window.allPortsLayer && map.hasLayer(window.allPortsLayer)) {
        map.removeLayer(window.allPortsLayer);
        delete window.allPortsLayer;
        showNotification('Все порты скрыты', 'info');
    } else {
        await showAllPortsOnMap();
    }
}

async function showAllPortsOnMap() {
    showLoader('Загрузка портов...');
    try {
        const response = await fetch(`${API_URL}/ports/map`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();

        if (data.success && data.ports && data.ports.length > 0) {
            if (window.allPortsLayer) map.removeLayer(window.allPortsLayer);
            window.allPortsLayer = L.layerGroup();

            const portsToShow = data.ports.slice(0, 500);

            portsToShow.forEach(port => {
                const markerHtml = '<div style="background:#3498db;width:8px;height:8px;border-radius:50%;border:2px solid white;"></div>';
                L.marker([port.lat, port.lon], {
                    icon: L.divIcon({ html: markerHtml, iconSize: [8, 8], iconAnchor: [4, 4] }),
                    title: port.name
                }).bindPopup(`<b>${port.name}</b><br>${port.country || ''}<br>${port.lat.toFixed(4)}, ${port.lon.toFixed(4)}`)
                  .addTo(window.allPortsLayer);
            });

            window.allPortsLayer.addTo(map);

            if (portsToShow.length > 10) {
                const bounds = L.latLngBounds(portsToShow.map(p => [p.lat, p.lon]));
                map.fitBounds(bounds, { padding: [100, 100] });
            }

            showNotification(`Показано ${portsToShow.length} портов`, 'success');
        }
    } catch (error) {
        console.error('❌ Ошибка:', error);
        showNotification('Ошибка загрузки портов', 'error');
    } finally {
        hideLoader();
    }
}

function clearMap() {
    clearMapMarkers();

    const routeInfo = document.getElementById('route-info');
    if (routeInfo) routeInfo.style.display = 'none';

    const aiList = document.getElementById('ai-list');
    if (aiList) aiList.innerHTML = '<li>Рассчитайте маршрут для получения рекомендаций</li>';

    const weatherInfo = document.getElementById('weather-info');
    if (weatherInfo) weatherInfo.style.display = 'none';

    const modeBar = document.getElementById('mode-bar');
    if (modeBar) modeBar.innerHTML = '';

    if (window.allPortsLayer && map) {
        map.removeLayer(window.allPortsLayer);
        delete window.allPortsLayer;
    }

    if (map) {
        map.setView([50, 30], 3);
        map.invalidateSize();
    }

    showNotification('Карта очищена', 'info');
}

function clearMapMarkers() {
    if (routeLayer && map) { map.removeLayer(routeLayer); routeLayer = null; }
    if (departureMarker && map) { map.removeLayer(departureMarker); departureMarker = null; }
    if (destinationMarker && map) { map.removeLayer(destinationMarker); destinationMarker = null; }
}

function showNotification(message, type = 'info') {
    const oldNotification = document.querySelector('.notification');
    if (oldNotification) oldNotification.remove();

    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);

    setTimeout(() => {
        if (notification.parentNode) {
            notification.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => notification.remove(), 300);
        }
    }, 5000);
}

function showLoader(text) {
    const loader = document.getElementById('loader');
    const loaderText = document.getElementById('loader-text');
    if (loader) loader.style.display = 'block';
    if (loaderText) loaderText.textContent = text;
}

function hideLoader() {
    const loader = document.getElementById('loader');
    if (loader) loader.style.display = 'none';
}

setInterval(checkServerStatus, 30000);

const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
    @keyframes slideOut { from { transform: translateX(0); opacity: 1; } to { transform: translateX(100%); opacity: 0; } }
`;
document.head.appendChild(style);

console.log('✅ app.js загружен');