(() => {
  "use strict";

  // Şehir merkezleri için WGS84 (latitude/longitude) koordinatları.
  // Bu katalog, dışarıya API anahtarı vermeden net konum gösteren güvenli web demo katmanıdır.
  const GPS_CITIES = {
    istanbul: { lat: 41.0082, lon: 28.9784, name: "İstanbul", address: "Fatih, İstanbul" },
    ankara: { lat: 39.9334, lon: 32.8597, name: "Ankara", address: "Çankaya, Ankara" },
    izmir: { lat: 38.4237, lon: 27.1428, name: "İzmir", address: "Konak, İzmir" },
    antalya: { lat: 36.8969, lon: 30.7133, name: "Antalya", address: "Muratpaşa, Antalya" },
    bursa: { lat: 40.1950, lon: 29.0600, name: "Bursa", address: "Osmangazi, Bursa" },
    konya: { lat: 37.8714, lon: 32.4846, name: "Konya", address: "Selçuklu, Konya" },
    adana: { lat: 37.0000, lon: 35.3213, name: "Adana", address: "Seyhan, Adana" },
    gaziantep: { lat: 37.0662, lon: 37.3833, name: "Gaziantep", address: "Şahinbey, Gaziantep" },
    trabzon: { lat: 41.0015, lon: 39.7178, name: "Trabzon", address: "Ortahisar, Trabzon" },
    samsun: { lat: 41.2867, lon: 36.3300, name: "Samsun", address: "İlkadım, Samsun" },
    kayseri: { lat: 38.7225, lon: 35.4875, name: "Kayseri", address: "Melikgazi, Kayseri" },
    diyarbakir: { lat: 37.9144, lon: 40.2306, name: "Diyarbakır", address: "Sur, Diyarbakır" },
    elazig: { lat: 38.6810, lon: 39.2264, name: "Elazığ", address: "Elazığ Merkez" },
    eskisehir: { lat: 39.7667, lon: 30.5256, name: "Eskişehir", address: "Odunpazarı, Eskişehir" }
  };

  const EARTH_RADIUS_KM = 6371.0088;
  const REFERENCE_SPEED_KMH = 70;
  let routeMap;
  let routeLayer;

  const normalize = value => value.toLocaleLowerCase("tr-TR")
    .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .replaceAll("ı", "i").replaceAll("ş", "s").replaceAll("ğ", "g")
    .replaceAll("ü", "u").replaceAll("ö", "o").replaceAll("ç", "c");

  function permutations(values) {
    if (values.length <= 1) return [values.slice()];
    const result = [];
    values.forEach((value, index) => {
      const rest = values.slice(0, index).concat(values.slice(index + 1));
      permutations(rest).forEach(permutation => result.push([value, ...permutation]));
    });
    return result;
  }

  function toRadians(value) { return value * Math.PI / 180; }

  function haversineKm(a, b) {
    const lat = toRadians(b.lat - a.lat);
    const lon = toRadians(b.lon - a.lon);
    const h = Math.sin(lat / 2) ** 2
      + Math.cos(toRadians(a.lat)) * Math.cos(toRadians(b.lat)) * Math.sin(lon / 2) ** 2;
    return 2 * EARTH_RADIUS_KM * Math.asin(Math.min(1, Math.sqrt(h)));
  }

  function distanceMatrix(cities) {
    return cities.map(from => cities.map(to => from === to ? 0 : haversineKm(from, to)));
  }

  function routeCost(route, matrix) {
    return route.reduce((sum, current, index) => sum + matrix[current][route[(index + 1) % route.length]], 0);
  }

  function exact(cities, matrix) {
    const started = performance.now();
    const tails = permutations(Array.from({ length: cities.length - 1 }, (_, index) => index + 1));
    let bestRoute = null;
    let bestCost = Infinity;
    tails.forEach(tail => {
      const route = [0, ...tail];
      const cost = routeCost(route, matrix);
      if (cost < bestCost) {
        bestRoute = route;
        bestCost = cost;
      }
    });
    return { name: "Kesin kontrol", route: bestRoute, cost: bestCost, ms: performance.now() - started, cls: "exact" };
  }

  function anneal(cities, matrix) {
    const started = performance.now();
    let current = Array.from({ length: cities.length }, (_, index) => index);
    for (let index = current.length - 1; index > 1; index--) {
      const swap = 1 + Math.floor(Math.random() * index);
      [current[index], current[swap]] = [current[swap], current[index]];
    }
    let currentCost = routeCost(current, matrix);
    let bestRoute = current.slice();
    let bestCost = currentCost;
    let temperature = 120;
    for (let step = 0; step < 5000; step++) {
      const first = 1 + Math.floor(Math.random() * (cities.length - 1));
      const second = 1 + Math.floor(Math.random() * (cities.length - 1));
      if (first === second) continue;
      const candidate = current.slice();
      [candidate[first], candidate[second]] = [candidate[second], candidate[first]];
      const cost = routeCost(candidate, matrix);
      const delta = cost - currentCost;
      if (delta < 0 || Math.random() < Math.exp(-delta / Math.max(temperature, 0.0001))) {
        current = candidate;
        currentCost = cost;
        if (cost < bestCost) {
          bestRoute = candidate.slice();
          bestCost = cost;
        }
      }
      temperature *= 0.9985;
    }
    return { name: "Klasik hızlı", route: bestRoute, cost: bestCost, ms: performance.now() - started, cls: "fast" };
  }

  function quantumModel(cities, matrix) {
    const started = performance.now();
    const tours = permutations(Array.from({ length: cities.length - 1 }, (_, index) => index + 1)).map(tail => [0, ...tail]);
    const costs = tours.map(route => routeCost(route, matrix));
    const minimum = Math.min(...costs);
    const maximum = Math.max(...costs);
    const temperature = Math.max((maximum - minimum) / 4, 0.05);
    const amplitudes = costs.map(cost => Math.exp(-(cost - minimum) / temperature));
    const total = amplitudes.reduce((sum, value) => sum + value, 0);
    const probabilities = amplitudes.map(value => value / total);
    let bestIndex = 0;
    for (let shot = 0; shot < 512; shot++) {
      let pick = Math.random();
      let cumulative = 0;
      for (let index = 0; index < probabilities.length; index++) {
        cumulative += probabilities[index];
        if (pick <= cumulative) {
          if (costs[index] < costs[bestIndex]) bestIndex = index;
          break;
        }
      }
    }
    const peak = Math.max(...probabilities);
    return {
      name: "Kuantum modeli",
      route: tours[bestIndex],
      cost: costs[bestIndex],
      ms: performance.now() - started,
      cls: "quantum",
      detail: `En güçlü olasılık rastgele seçime göre ${(peak * tours.length).toFixed(2)}× güçlendirildi.`
    };
  }

  function parseCities(text) {
    const source = normalize(text);
    return Object.entries(GPS_CITIES)
      .filter(([key]) => source.includes(key))
      .map(([key, city]) => ({ key, ...city }));
  }

  function formatKm(value) {
    return `${value.toLocaleString("tr-TR", { maximumFractionDigits: 1 })} km`;
  }

  function durationMinutes(route, matrix) {
    return routeCost(route, matrix) / REFERENCE_SPEED_KMH * 60;
  }

  function formatDuration(minutes) {
    const rounded = Math.round(minutes);
    if (rounded < 60) return `${rounded} dk`;
    return `${Math.floor(rounded / 60)} sa ${rounded % 60} dk`;
  }

  function osmLink(city) {
    return `https://www.openstreetmap.org/?mlat=${city.lat}&mlon=${city.lon}#map=11/${city.lat}/${city.lon}`;
  }

  function renderLocations(cities, result) {
    const panel = document.getElementById("locations");
    panel.hidden = false;
    panel.innerHTML = result.route.map((cityIndex, order) => {
      const city = cities[cityIndex];
      return `<article class="location-card">
        <span class="location-order">${order + 1}</span>
        <div><strong>${city.name}</strong><span>${city.address} · ${city.lat.toFixed(4)}° N, ${city.lon.toFixed(4)}° E</span></div>
        <a href="${osmLink(city)}" target="_blank" rel="noopener noreferrer">Haritada aç ↗</a>
      </article>`;
    }).join("");
  }

  function drawFallback(cities, result) {
    const svg = document.getElementById("route");
    const width = 720;
    const height = 300;
    const padding = 42;
    const lons = cities.map(city => city.lon);
    const lats = cities.map(city => city.lat);
    const minLon = Math.min(...lons);
    const maxLon = Math.max(...lons);
    const minLat = Math.min(...lats);
    const maxLat = Math.max(...lats);
    const x = lon => padding + (lon - minLon) / Math.max(maxLon - minLon, 0.2) * (width - 2 * padding);
    const y = lat => height - padding - (lat - minLat) / Math.max(maxLat - minLat, 0.2) * (height - 2 * padding);
    const closedRoute = [...result.route, result.route[0]];
    const points = closedRoute.map(index => `${x(cities[index].lon)},${y(cities[index].lat)}`).join(" ");
    const nodes = cities.map((city, index) => `
      <circle cx="${x(city.lon)}" cy="${y(city.lat)}" r="10" fill="#7566ff" stroke="#fff" stroke-width="2"/>
      <text x="${x(city.lon)}" y="${y(city.lat) + 4}" fill="#fff" font-size="11" font-weight="700" text-anchor="middle">${result.route.indexOf(index) + 1}</text>
      <text x="${x(city.lon)}" y="${y(city.lat) - 18}" fill="#eaf0ff" font-size="13" text-anchor="middle">${city.name}</text>`).join("");
    svg.innerHTML = `<polyline points="${points}" fill="none" stroke="#37d4f5" stroke-width="4" stroke-linejoin="round"/>${nodes}`;
    svg.hidden = false;
    document.getElementById("map").hidden = true;
    return false;
  }

  function renderMap(cities, result) {
    if (!window.L) return drawFallback(cities, result);
    const mapHost = document.getElementById("map");
    const svg = document.getElementById("route");
    mapHost.hidden = false;
    svg.hidden = true;
    if (!routeMap) {
      routeMap = window.L.map(mapHost, { scrollWheelZoom: false, zoomControl: true });
      window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "&copy; <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap contributors</a>"
      }).addTo(routeMap);
    }
    if (routeLayer) routeLayer.clearLayers();
    routeLayer = window.L.layerGroup().addTo(routeMap);
    const points = result.route.map(index => [cities[index].lat, cities[index].lon]);
    routeLayer.addLayer(window.L.polyline([...points, points[0]], { color: "#37d4f5", weight: 4, opacity: 0.92 }));
    result.route.forEach((cityIndex, order) => {
      const city = cities[cityIndex];
      const marker = window.L.circleMarker([city.lat, city.lon], {
        radius: 11,
        color: "#ffffff",
        weight: 2,
        fillColor: "#7566ff",
        fillOpacity: 1
      });
      marker.bindTooltip(`${order + 1}. ${city.name}`, { direction: "top", offset: [0, -8] });
      marker.bindPopup(`<strong>${order + 1}. ${city.name}</strong><br>${city.address}<br>${city.lat.toFixed(4)}° N, ${city.lon.toFixed(4)}° E<br><a href="${osmLink(city)}" target="_blank" rel="noopener noreferrer">OpenStreetMap'te aç ↗</a>`);
      routeLayer.addLayer(marker);
    });
    routeMap.fitBounds(window.L.latLngBounds(points), { padding: [28, 28], maxZoom: 7 });
    window.setTimeout(() => routeMap.invalidateSize(), 0);
    return true;
  }

  function renderLegs(cities, result, matrix) {
    const legs = document.getElementById("legs");
    const closedRoute = [...result.route, result.route[0]];
    legs.innerHTML = closedRoute.slice(0, -1).map((from, index) => {
      const to = closedRoute[index + 1];
      return `<div class="leg"><span>${index + 1}. ${cities[from].name} → ${cities[to].name}</span><strong>${formatKm(matrix[from][to])}</strong></div>`;
    }).join("");
  }

  const previousButton = document.getElementById("solve");
  const solveButton = previousButton.cloneNode(true);
  previousButton.replaceWith(solveButton);

  solveButton.addEventListener("click", () => {
    const status = document.getElementById("status");
    let cities = parseCities(document.getElementById("problem").value);
    if (cities.length < 3) {
      status.style.color = "var(--red)";
      status.textContent = "En az üç tanınan şehir yazmalısın.";
      return;
    }
    if (cities.length > 8) {
      cities = cities.slice(0, 8);
      status.textContent = "Web demosu güvenli çalışma için ilk 8 şehri kullandı.";
    } else {
      status.textContent = `${cities.length} şehir gerçek GPS merkeziyle eşleşti. Üç motor çalıştırıldı.`;
    }
    status.style.color = "var(--green)";

    const matrix = distanceMatrix(cities);
    const results = [exact(cities, matrix), anneal(cities, matrix), quantumModel(cities, matrix)];
    const best = results.reduce((first, second) => first.cost <= second.cost ? first : second);
    const tours = Array.from({ length: cities.length - 1 }, (_, index) => index + 1).reduce((total, value) => total * value, 1);
    const renderedMap = renderMap(cities, best);
    const minutes = durationMinutes(best.route, matrix);

    document.getElementById("result-title").textContent = `${cities.length} şehir, ${results.length} yöntem, gerçek GPS koordinatları`;
    document.getElementById("best-distance").textContent = formatKm(best.cost);
    document.getElementById("best-duration").textContent = formatDuration(minutes);
    document.getElementById("best-method").textContent = best.name;
    document.getElementById("state-space").textContent = tours.toLocaleString("tr-TR");
    document.getElementById("map-source").textContent = `${renderedMap ? "Harita: OpenStreetMap · " : "Harita yedek görünümü · "}Konum: şehir merkezi GPS koordinatları · Mesafe: kuş uçuşu Haversine km · Süre: ${REFERENCE_SPEED_KMH} km/sa referans hız · Gerçek sürüş ve trafik verisi değildir.`;
    renderLocations(cities, best);
    renderLegs(cities, best, matrix);
    document.getElementById("methods").innerHTML = results.map(result => `
      <div class="method ${result.cls}"><strong>${result.name}</strong>
        <small>${formatKm(result.cost)} kuş uçuşu · ${result.ms.toFixed(2)} ms</small>
        <small>${result.route.map(index => cities[index].name).join(" → ")} → ${cities[result.route[0]].name}</small>
        ${result.detail ? `<small>${result.detail}</small>` : ""}
      </div>`).join("");
  });
})();
