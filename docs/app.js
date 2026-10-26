(() => {
  "use strict";

  // Şehir merkezleri için WGS84 (latitude/longitude) referans koordinatları.
  // Bu katalog, dışarıya API anahtarı vermeden net konum gösteren güvenli web katmanıdır.
  // Büyük şehirlerde tek bir evrensel merkez noktası olmadığı için bunlar kapı/adres değil,
  // kullanıcı tarafından OpenStreetMap üzerinde doğrulanabilen şehir merkezi referanslarıdır.
  const GPS_CITIES = {
    istanbul: { lat: 41.0082, lon: 28.9784, name: "İstanbul", reference: "Fatih şehir merkezi" },
    ankara: { lat: 39.9334, lon: 32.8597, name: "Ankara", reference: "Çankaya şehir merkezi" },
    izmir: { lat: 38.4237, lon: 27.1428, name: "İzmir", reference: "Konak şehir merkezi" },
    antalya: { lat: 36.8969, lon: 30.7133, name: "Antalya", reference: "Muratpaşa şehir merkezi" },
    bursa: { lat: 40.1950, lon: 29.0600, name: "Bursa", reference: "Osmangazi şehir merkezi" },
    konya: { lat: 37.8714, lon: 32.4846, name: "Konya", reference: "Selçuklu şehir merkezi" },
    adana: { lat: 37.0000, lon: 35.3213, name: "Adana", reference: "Seyhan şehir merkezi" },
    gaziantep: { lat: 37.0662, lon: 37.3833, name: "Gaziantep", reference: "Şahinbey şehir merkezi" },
    trabzon: { lat: 41.0015, lon: 39.7178, name: "Trabzon", reference: "Ortahisar şehir merkezi" },
    samsun: { lat: 41.2867, lon: 36.3300, name: "Samsun", reference: "İlkadım şehir merkezi" },
    kayseri: { lat: 38.7225, lon: 35.4875, name: "Kayseri", reference: "Melikgazi şehir merkezi" },
    diyarbakir: { lat: 37.9144, lon: 40.2306, name: "Diyarbakır", reference: "Sur şehir merkezi" },
    elazig: { lat: 38.6810, lon: 39.2264, name: "Elazığ", reference: "Elazığ merkez" },
    eskisehir: { lat: 39.7667, lon: 30.5256, name: "Eskişehir", reference: "Odunpazarı şehir merkezi" }
  };

  const EARTH_RADIUS_KM = 6371.0088;
  const REFERENCE_SPEED_KMH = 70;
  // This URL is intentionally public: it points to a server-side proxy, never
  // to Azure Maps directly. Credentials stay in that proxy's environment.
  const API_BASE_URL = String(window.QUANTUM_ROUTE_CONFIG?.apiBaseUrl || "")
    .trim()
    .replace(/\/+$/, "");
  let routeMap;
  let routeLayer;
  let latestShareSummary = "";
  let adminLocations = [];
  let selectedStops = [];
  let placeSearchTimer;
  let placeSearchAbort;
  let placeSearchVersion = 0;

  // V2 ağ bölme senaryosu: ağırlık, iki iş arasındaki iş bağımlılığının gücüdür.
  // Kullanıcının metni yalnızca bu açık, görünür senaryodaki düğümleri seçer.
  const MAXCUT_SCENARIO = {
    nodes: [
      { id: "odeme", label: "Ödeme" },
      { id: "kargo", label: "Kargo" },
      { id: "iade", label: "İade" },
      { id: "teslimat", label: "Teslimat" },
      { id: "kampanya", label: "Kampanya" }
    ],
    edges: [
      { source: "odeme", target: "iade", weight: 9 },
      { source: "kargo", target: "teslimat", weight: 8 },
      { source: "iade", target: "kampanya", weight: 7 },
      { source: "teslimat", target: "kampanya", weight: 6 },
      { source: "odeme", target: "kampanya", weight: 5 },
      { source: "kargo", target: "iade", weight: 4 },
      { source: "odeme", target: "kargo", weight: 3 }
    ]
  };

  const normalize = value => value.toLocaleLowerCase("tr-TR")
    .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .replaceAll("ı", "i").replaceAll("ş", "s").replaceAll("ğ", "g")
    .replaceAll("ü", "u").replaceAll("ö", "o").replaceAll("ç", "c");

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, character => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"
    })[character]);
  }

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

  function isSquareNumericMatrix(matrix, size) {
    return Array.isArray(matrix)
      && matrix.length === size
      && matrix.every(row => Array.isArray(row)
        && row.length === size
        && row.every(value => Number.isFinite(Number(value)) && Number(value) >= 0));
  }

  async function fetchRoadMatrix(cities) {
    if (!API_BASE_URL) return null;
    const response = await fetch(`${API_BASE_URL}/maps/route-matrix`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        locations: routeRequestLocations(cities).map(city => ({
          name: city.name,
          point: { latitude: city.lat, longitude: city.lon }
        })),
        traffic: "historical"
      })
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || "Gerçek yol servisi şu anda yanıt vermiyor.");
    }
    if (!isSquareNumericMatrix(payload.distance_meters, cities.length)
      || !isSquareNumericMatrix(payload.duration_seconds, cities.length)) {
      throw new Error("Gerçek yol servisi eksik bir matris döndürdü.");
    }
    return {
      distanceKm: payload.distance_meters.map(row => row.map(value => Number(value) / 1000)),
      durationSeconds: payload.duration_seconds.map(row => row.map(Number)),
      traffic: payload.traffic || "historical"
    };
  }

  function routeRequestLocations(cities) {
    const used = new Map();
    return cities.map((city, index) => {
      const base = String(city.routeName || city.name || `Durak ${index + 1}`)
        .trim().slice(0, 52) || `Durak ${index + 1}`;
      const count = (used.get(base) || 0) + 1;
      used.set(base, count);
      // Azure Maps matrisi benzersiz isim ister. Aynı zincirin iki şubesi
      // adresiyle, gerekirse sıra numarasıyla ayrı rota durakları olur.
      const suffix = count > 1 ? ` · ${count}` : "";
      return { ...city, name: `${base.slice(0, 60 - suffix.length)}${suffix}` };
    });
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
      .map(([key, city]) => ({ key, ...city, kind: "İl", source: "WGS84 şehir merkezi referansı" }));
  }

  function validPoint(lat, lon) {
    return Number.isFinite(lat) && Number.isFinite(lon)
      && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180;
  }

  // Kaynak veri, bazı Türkçe dotless-i karakterlerini ASCII biçiminde verir.
  // Arama normalizasyonu bunu zaten tolere eder; bu küçük görünüm düzeltmeleri
  // ise ziyaretçiye doğal Türkçe ilçe adını gösterir.
  const CATALOG_NAME_OVERRIDES = Object.freeze({
    TUR001011: "Sarıçam", TUR002001: "Adıyaman", TUR003014: "Kızılören",
    TUR006018: "Kızılcahamam", TUR018007: "Kızılırmak", TUR026011: "Sarıcakaya",
    TUR034023: "Kadıköy", TUR034030: "Sarıyer", TUR036006: "Sarıkamış",
    TUR038011: "Sarıoğlan", TUR038012: "Sarız", TUR042020: "Kadınhanı",
    TUR045011: "Sarıgöl", TUR047004: "Kızıltepe", TUR050001: "Acıgöl",
    TUR055010: "İlkadım", TUR066007: "Kadışehri", TUR066009: "Sarıkaya",
    TUR068007: "Sarıyahşi", TUR070006: "Sarıveliler",
    TUR003: "Afyonkarahisar", TUR026: "Eskişehir", TUR038: "Kayseri",
    TUR045: "Manisa", TUR047: "Mardin", TUR050: "Nevşehir", TUR080: "Osmaniye"
  });

  function catalogDisplayName(value, id) {
    const cleaned = String(value || "").normalize("NFC").replaceAll("\u0307", "");
    return CATALOG_NAME_OVERRIDES[id] || cleaned;
  }

  function localPlace({ id, name, provinceName = "", lat, lon, kind }) {
    const latitude = Number(lat);
    const longitude = Number(lon);
    if (!id || !name || !validPoint(latitude, longitude)) return null;
    const displayName = kind === "İlçe" ? `${name}, ${provinceName}` : name;
    return {
      key: `catalog:${kind}:${id}`,
      name: displayName,
      lat: latitude,
      lon: longitude,
      kind,
      reference: kind === "İlçe"
        ? `${provinceName} · ilçe idari alan referans noktası`
        : "il idari alan referans noktası",
      source: "Türkiye il/ilçe kataloğu"
    };
  }

  async function loadAdminCatalog() {
    const note = document.getElementById("place-note");
    try {
      // GitHub Pages dağıtımı sırasında eski bir 404 yanıtını önbellekten alma.
      // Veri küçük ve sürümü sayfayla birlikte güncelleniyor; bu nedenle güncel
      // katalog yanıtını doğrulamak, ilk aramanın boş kalmamasından daha önemlidir.
      const response = await fetch("./data/turkiye-il-ilce-konumlari.json?v=2026-10-26", { cache: "no-cache" });
      if (!response.ok) throw new Error("Katalog yüklenemedi.");
      const payload = await response.json();
      const provinces = Array.isArray(payload.provinces) ? payload.provinces : [];
      const districts = Array.isArray(payload.districts) ? payload.districts : [];
      adminLocations = [
        ...provinces.map(record => localPlace({
          ...record, name: catalogDisplayName(record.name, record.id), kind: "İl"
        })),
        ...districts.map(record => localPlace({
          ...record,
          name: catalogDisplayName(record.name, record.id),
          provinceName: catalogDisplayName(record.provinceName, record.provinceId),
          kind: "İlçe"
        }))
      ].filter(Boolean);
      if (adminLocations.length < 1_000) throw new Error("Katalog eksik.");
      note.innerHTML = "<strong>81 il ve 973 ilçe hazır.</strong> İl/ilçe araması bu sayfada çalışır. <strong>Adres ve mağaza:</strong> Azure Maps bağlantısı açıksa sonuçlardan doğru olanı sen seçersin. Rota için 3–8 durak ekleyebilirsin.";
    } catch {
      // Katalog hatası rota laboratuvarını bozmaz; mevcut şehir örneği yine çalışır.
      note.textContent = "İlçe kataloğu yüklenemedi. Örnek şehir rotası yine çalışır; adres ve mağaza araması için Azure Maps bağlantısı gerekir.";
    }
  }

  function placeSearchTerms(value) {
    return normalize(value).replace(/[^a-z0-9\s]/g, " ").split(/\s+/).filter(Boolean);
  }

  function findLocalPlaces(query) {
    const terms = placeSearchTerms(query);
    if (!terms.length || !adminLocations.length) return [];
    const compact = terms.join(" ");
    return adminLocations
      .map(place => {
        const name = placeSearchTerms(place.name).join(" ");
        const reference = normalize(place.reference);
        const exact = name === compact;
        const starts = name.startsWith(compact);
        const allTerms = terms.every(term => name.includes(term) || reference.includes(term));
        if (!exact && !starts && !allTerms) return null;
        return { place, score: exact ? 30 : starts ? 20 : 10 };
      })
      .filter(Boolean)
      .sort((first, second) => second.score - first.score || first.place.name.localeCompare(second.place.name, "tr"))
      .slice(0, 5)
      .map(item => item.place);
  }

  function isExactLocalMatch(query, places) {
    const compact = placeSearchTerms(query).join(" ");
    return places.some(place => placeSearchTerms(place.name).join(" ") === compact);
  }

  function remotePlace(candidate, index) {
    const latitude = Number(candidate?.point?.latitude);
    const longitude = Number(candidate?.point?.longitude);
    const label = String(candidate?.label || "").trim();
    if (!label || !validPoint(latitude, longitude)) return null;
    const kind = candidate.kind === "poi" ? "Mağaza / işletme" : "Adres / konum";
    const detail = String(candidate.address || candidate.category || candidate.reference || "Azure Maps sonucu").trim();
    const routeName = `${label} · ${detail}`.slice(0, 60);
    return {
      key: `azure:${latitude.toFixed(6)}:${longitude.toFixed(6)}:${normalize(label)}:${index}`,
      name: label.slice(0, 180),
      lat: latitude,
      lon: longitude,
      kind,
      reference: detail.slice(0, 240),
      routeName,
      source: "Azure Maps"
    };
  }

  function mergePlaces(first, second) {
    const seen = new Set();
    return [...first, ...second].filter(place => {
      const key = `${normalize(place.name)}:${place.lat.toFixed(4)}:${place.lon.toFixed(4)}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    }).slice(0, 5);
  }

  function placeKindText(place) {
    return place.kind || "Konum";
  }

  function renderPlaceResults(places, message = "") {
    const host = document.getElementById("place-results");
    host.replaceChildren();
    if (!places.length && !message) {
      host.hidden = true;
      return;
    }
    host.hidden = false;
    if (message) {
      const note = document.createElement("small");
      note.className = "place-note";
      note.textContent = message;
      host.appendChild(note);
    }
    places.forEach(place => {
      const button = document.createElement("button");
      button.className = "place-result";
      button.type = "button";
      const details = document.createElement("span");
      const title = document.createElement("strong");
      title.textContent = place.name;
      const detail = document.createElement("small");
      detail.textContent = `${place.reference} · ${place.lat.toFixed(4)}°, ${place.lon.toFixed(4)}°`;
      const kind = document.createElement("span");
      kind.className = "place-kind";
      kind.textContent = placeKindText(place);
      details.append(title, detail);
      button.append(details, kind);
      button.addEventListener("click", () => addSelectedStop(place));
      host.appendChild(button);
    });
  }

  function renderSelectedStops() {
    const host = document.getElementById("selected-stops");
    host.replaceChildren();
    selectedStops.forEach((place, index) => {
      const chip = document.createElement("span");
      chip.className = "stop-chip";
      const label = document.createElement("span");
      label.textContent = `${index + 1}. ${place.name}`;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.title = `${place.name} durağını kaldır`;
      remove.setAttribute("aria-label", `${place.name} durağını kaldır`);
      remove.textContent = "×";
      remove.addEventListener("click", () => {
        selectedStops = selectedStops.filter(stop => stop.key !== place.key);
        renderSelectedStops();
      });
      chip.append(label, remove);
      host.appendChild(chip);
    });
  }

  function setPlaceStatus(message, color = "var(--muted)") {
    const status = document.getElementById("status");
    status.style.color = color;
    status.textContent = message;
  }

  function addSelectedStop(place) {
    if (selectedStops.some(stop => stop.key === place.key)) {
      setPlaceStatus(`${place.name} zaten duraklara eklendi.`, "var(--amber)");
      return;
    }
    if (selectedStops.length >= 8) {
      setPlaceStatus("Rota laboratuvarı için en fazla 8 durak ekleyebilirsin.", "var(--amber)");
      return;
    }
    selectedStops = [...selectedStops, place];
    renderSelectedStops();
    document.getElementById("place-query").value = "";
    renderPlaceResults([]);
    setPlaceStatus(`${place.name} eklendi. En az 3 durak seçip rotayı çözebilirsin.`, "var(--green)");
  }

  async function fetchRemotePlaces(query, signal) {
    if (!API_BASE_URL) return [];
    const response = await fetch(`${API_BASE_URL}/maps/places`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, top: 5 }),
      signal
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Konum servisi yanıt vermedi.");
    return Array.isArray(payload.candidates)
      ? payload.candidates.map(remotePlace).filter(Boolean)
      : [];
  }

  async function searchPlaces(query) {
    const version = ++placeSearchVersion;
    const cleaned = String(query || "").trim();
    if (cleaned.length < 2) {
      renderPlaceResults([]);
      return;
    }
    const local = findLocalPlaces(cleaned);
    if (isExactLocalMatch(cleaned, local)) {
      renderPlaceResults(local, "Bu ilçe/il sayfadaki doğrulanabilir idari alan kataloğundan geldi.");
      return;
    }
    if (!API_BASE_URL) {
      const message = local.length
        ? "İl/ilçe eşleşmeleri gösteriliyor. Mağaza veya açık adres araması için Azure Maps bağlantısı henüz yayımlanmadı."
        : "Bu ifade il/ilçe kataloğunda yok. Mağaza ve açık adres araması için Azure Maps bağlantısı henüz yayımlanmadı.";
      renderPlaceResults(local, message);
      return;
    }
    if (placeSearchAbort) placeSearchAbort.abort();
    placeSearchAbort = new AbortController();
    renderPlaceResults(local, "Adres ve işletme eşleşmeleri güvenli konum servisinden aranıyor…");
    try {
      const remote = await fetchRemotePlaces(cleaned, placeSearchAbort.signal);
      if (version !== placeSearchVersion) return;
      renderPlaceResults(mergePlaces(local, remote), remote.length
        ? "Doğru sonucu listeden seç. Sağlayıcı konumu otomatik olarak rotaya eklenmez."
        : "Bu arama için doğrulanmış bir sonuç bulunamadı; daha ayrıntılı ilçe veya adres eklemeyi dene.");
    } catch (error) {
      if (error?.name === "AbortError" || version !== placeSearchVersion) return;
      renderPlaceResults(local, `Konum servisi şu an yanıt vermedi. ${error instanceof Error ? error.message : ""}`.trim());
    }
  }

  function setupPlacePicker() {
    const input = document.getElementById("place-query");
    input.addEventListener("input", () => {
      window.clearTimeout(placeSearchTimer);
      const value = input.value;
      placeSearchTimer = window.setTimeout(() => searchPlaces(value), 280);
    });
    input.addEventListener("keydown", event => {
      if (event.key === "Escape") {
        input.value = "";
        renderPlaceResults([]);
      }
    });
    loadAdminCatalog();
  }

  function formatKm(value) {
    return `${value.toLocaleString("tr-TR", { maximumFractionDigits: 1 })} km`;
  }

  function durationMinutes(route, matrix, durationSeconds = null) {
    if (durationSeconds) return routeCost(route, durationSeconds) / 60;
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
    panel.replaceChildren();
    result.route.forEach((cityIndex, order) => {
      const city = cities[cityIndex];
      const card = document.createElement("article");
      card.className = "location-card";
      const orderLabel = document.createElement("span");
      orderLabel.className = "location-order";
      orderLabel.textContent = String(order + 1);
      const copy = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = city.name;
      const detail = document.createElement("span");
      detail.textContent = `WGS84 · ${city.reference} · ${city.lat.toFixed(4)}° N, ${city.lon.toFixed(4)}° E`;
      const link = document.createElement("a");
      link.href = osmLink(city);
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "Haritada aç ↗";
      copy.append(title, detail);
      card.append(orderLabel, copy, link);
      panel.appendChild(card);
    });
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
      <text x="${x(city.lon)}" y="${y(city.lat) - 18}" fill="#eaf0ff" font-size="13" text-anchor="middle">${escapeSvgText(city.name)}</text>`).join("");
    svg.innerHTML = `<polyline points="${points}" fill="none" stroke="#37d4f5" stroke-width="4" stroke-linejoin="round"/>${nodes}`;
    svg.hidden = false;
    document.getElementById("map").hidden = true;
    document.getElementById("route-legend").hidden = false;
    return false;
  }

  function renderMap(cities, result) {
    if (!window.L) return drawFallback(cities, result);
    const mapHost = document.getElementById("map");
    const svg = document.getElementById("route");
    mapHost.hidden = false;
    svg.hidden = true;
    document.getElementById("route-legend").hidden = false;
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
      marker.bindTooltip(`${order + 1}. ${escapeHtml(city.name)}`, { direction: "top", offset: [0, -8] });
      marker.bindPopup(`<strong>${order + 1}. ${escapeHtml(city.name)}</strong><br>WGS84 · ${escapeHtml(city.reference)}<br>${city.lat.toFixed(4)}° N, ${city.lon.toFixed(4)}° E<br><a href="${osmLink(city)}" target="_blank" rel="noopener noreferrer">OpenStreetMap'te aç ↗</a>`);
      routeLayer.addLayer(marker);
    });
    routeMap.fitBounds(window.L.latLngBounds(points), { padding: [28, 28], maxZoom: 7 });
    window.setTimeout(() => routeMap.invalidateSize(), 0);
    return true;
  }

  function renderLegs(cities, result, matrix, durationSeconds = null) {
    const legs = document.getElementById("legs");
    const closedRoute = [...result.route, result.route[0]];
    legs.innerHTML = closedRoute.slice(0, -1).map((from, index) => {
      const to = closedRoute[index + 1];
      const duration = durationSeconds
        ? ` · ${formatDuration(durationSeconds[from][to] / 60)}`
        : "";
      return `<div class="leg"><span>${index + 1}. ${escapeHtml(cities[from].name)} → ${escapeHtml(cities[to].name)}</span><strong>${formatKm(matrix[from][to])}${duration}</strong></div>`;
    }).join("");
  }

  function routeNames(cities, result) {
    return [...result.route, result.route[0]].map(index => cities[index].name).join(" → ");
  }

  function buildShareSummary(cities, result, roadMode, minutes) {
    const dataMode = roadMode
      ? "Azure Maps gerçek sürüş mesafesi ve süre verisi"
      : "WGS84 şehir merkezi GPS referanslarıyla kuş uçuşu Haversine hesabı";
    const durationLabel = roadMode ? "Tahmini sürüş süresi" : "Referans süre";
    return [
      "Quantum Route Lab üzerinde yeni bir rota deneyi yaptım.",
      "",
      `Duraklar: ${cities.map(city => city.name).join(", ")}`,
      `En iyi rota: ${routeNames(cities, result)}`,
      `Mesafe: ${formatKm(result.cost)} · ${durationLabel}: ${formatDuration(minutes)}`,
      `Veri modu: ${dataMode}.`,
      "",
      "Kuantum optimizasyonunu bir iddia olarak değil, klasik yöntemlerle aynı veri üzerinde karşılaştırılabilen açık bir deney olarak tasarlıyorum.",
      "#QuantumComputing #AzureQuantum #Optimization"
    ].join("\n");
  }

  function showShareSummary(summary, preview) {
    latestShareSummary = summary;
    document.getElementById("share-preview").textContent = preview;
    document.getElementById("share-card").hidden = false;
  }

  async function copyShareSummary(button) {
    if (!latestShareSummary) return;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(latestShareSummary);
      } else {
        const fallback = document.createElement("textarea");
        fallback.value = latestShareSummary;
        fallback.style.position = "fixed";
        fallback.style.opacity = "0";
        document.body.appendChild(fallback);
        fallback.select();
        const copied = document.execCommand("copy");
        fallback.remove();
        if (!copied) throw new Error("Tarayıcı kopyalama isteğini engelledi.");
      }
      button.textContent = "Kopyalandı ✓";
      window.setTimeout(() => { button.textContent = "Özeti kopyala"; }, 2200);
    } catch {
      button.textContent = "Kopyalanamadı";
      window.setTimeout(() => { button.textContent = "Özeti kopyala"; }, 2200);
    }
  }

  function maxCutNodesFromText(text) {
    const source = normalize(text);
    return MAXCUT_SCENARIO.nodes.filter(node => source.includes(normalize(node.label)));
  }

  function createMaxCutGraph(nodes) {
    const nodeIndex = new Map(nodes.map((node, index) => [node.id, index]));
    return MAXCUT_SCENARIO.edges
      .filter(edge => nodeIndex.has(edge.source) && nodeIndex.has(edge.target))
      .map(edge => ({
        ...edge,
        sourceIndex: nodeIndex.get(edge.source),
        targetIndex: nodeIndex.get(edge.target)
      }));
  }

  function enumerateMaxCutPartitions(size) {
    const partitions = [];
    // İlk düğümü A kümesinde sabitleyerek A/B ayna kopyalarını eleriz.
    for (let mask = 0; mask < 2 ** (size - 1); mask++) {
      const assignment = [true];
      for (let index = 1; index < size; index++) {
        assignment.push(Boolean(mask & (1 << (index - 1))));
      }
      if (!assignment.every(Boolean)) partitions.push(assignment);
    }
    return partitions;
  }

  function maxCutScore(assignment, edges) {
    return edges.reduce(
      (total, edge) => total + (assignment[edge.sourceIndex] !== assignment[edge.targetIndex] ? edge.weight : 0),
      0
    );
  }

  function groupsForAssignment(nodes, assignment) {
    return {
      a: nodes.filter((_, index) => assignment[index]).map(node => node.label),
      b: nodes.filter((_, index) => !assignment[index]).map(node => node.label)
    };
  }

  function exactMaxCut(nodes, edges) {
    const started = performance.now();
    const states = enumerateMaxCutPartitions(nodes.length);
    let best = states[0];
    let bestScore = maxCutScore(best, edges);
    states.slice(1).forEach(assignment => {
      const score = maxCutScore(assignment, edges);
      if (score > bestScore) {
        best = assignment;
        bestScore = score;
      }
    });
    return {
      name: "Kesin kontrol",
      assignment: best,
      score: bestScore,
      states: states.length,
      ms: performance.now() - started,
      cls: "exact",
      detail: `${states.length.toLocaleString("tr-TR")} benzersiz bölünmenin tamamı denetlendi.`
    };
  }

  function seededRandom(seed) {
    let value = seed >>> 0;
    return () => {
      value += 0x6D2B79F5;
      let mixed = value;
      mixed = Math.imul(mixed ^ (mixed >>> 15), mixed | 1);
      mixed ^= mixed + Math.imul(mixed ^ (mixed >>> 7), mixed | 61);
      return ((mixed ^ (mixed >>> 14)) >>> 0) / 4_294_967_296;
    };
  }

  function randomMaxCutPartition(size, random) {
    const assignment = Array.from({ length: size }, (_, index) => index === 0 || random() >= .5);
    if (assignment.every(Boolean)) assignment[assignment.length - 1] = false;
    return assignment;
  }

  function annealMaxCut(nodes, edges) {
    const started = performance.now();
    const iterations = 3_600;
    const random = seededRandom(20_261_026 + nodes.length * 101 + edges.length);
    let current = randomMaxCutPartition(nodes.length, random);
    let currentScore = maxCutScore(current, edges);
    let best = current.slice();
    let bestScore = currentScore;
    let accepted = 0;
    let temperature = Math.max(edges.reduce((total, edge) => total + edge.weight, 0) / 3, 1);
    const cooling = (0.02 / temperature) ** (1 / Math.max(iterations - 1, 1));

    for (let step = 0; step < iterations; step++) {
      const index = 1 + Math.floor(random() * (nodes.length - 1));
      const candidate = current.slice();
      candidate[index] = !candidate[index];
      if (candidate.every(Boolean)) continue;
      const candidateScore = maxCutScore(candidate, edges);
      const gain = candidateScore - currentScore;
      if (gain >= 0 || random() < Math.exp(gain / Math.max(temperature, .0001))) {
        current = candidate;
        currentScore = candidateScore;
        accepted++;
        if (currentScore > bestScore) {
          best = current.slice();
          bestScore = currentScore;
        }
      }
      temperature *= cooling;
    }

    return {
      name: "Klasik hızlı",
      assignment: best,
      score: bestScore,
      ms: performance.now() - started,
      cls: "fast",
      detail: `${iterations.toLocaleString("tr-TR")} bit-flip adımı · ${accepted.toLocaleString("tr-TR")} kabul.`
    };
  }

  function quantumMaxCutModel(nodes, edges) {
    const started = performance.now();
    const states = enumerateMaxCutPartitions(nodes.length);
    const scores = states.map(assignment => maxCutScore(assignment, edges));
    const highest = Math.max(...scores);
    const lowest = Math.min(...scores);
    const temperature = Math.max((highest - lowest) / 2.8, .75);
    // En yüksek kesime yakın durumları olasılıkta öne çıkaran şeffaf, eğitim amaçlı model.
    const amplitudes = scores.map(score => Math.exp((score - highest) / temperature));
    const amplitudeTotal = amplitudes.reduce((total, value) => total + value, 0);
    const probabilities = amplitudes.map(value => value / amplitudeTotal);
    const random = seededRandom(9_071 + nodes.length * 67 + edges.length);
    let bestIndex = 0;
    for (let shot = 0; shot < 512; shot++) {
      const pick = random();
      let cumulative = 0;
      for (let index = 0; index < probabilities.length; index++) {
        cumulative += probabilities[index];
        if (pick <= cumulative) {
          if (scores[index] > scores[bestIndex]) bestIndex = index;
          break;
        }
      }
    }
    const peakProbability = Math.max(...probabilities);
    return {
      name: "Kuantum olasılık modeli",
      assignment: states[bestIndex],
      score: scores[bestIndex],
      ms: performance.now() - started,
      cls: "quantum",
      detail: `En güçlü olasılık, eşit seçime göre ${(peakProbability * states.length).toFixed(2)}× öne çıktı.`
    };
  }

  function escapeSvgText(value) {
    return String(value).replace(/[&<>"']/g, character => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"
    })[character]);
  }

  function drawNetwork(nodes, edges, assignment) {
    const svg = document.getElementById("network");
    const centerX = 380;
    const centerY = 180;
    const radiusX = Math.min(252, 66 + nodes.length * 42);
    const radiusY = 112;
    const positions = nodes.map((node, index) => {
      const angle = -Math.PI / 2 + (Math.PI * 2 * index) / nodes.length;
      return { ...node, x: centerX + Math.cos(angle) * radiusX, y: centerY + Math.sin(angle) * radiusY };
    });
    const edgeMarkup = edges.map(edge => {
      const source = positions[edge.sourceIndex];
      const target = positions[edge.targetIndex];
      const cut = assignment[edge.sourceIndex] !== assignment[edge.targetIndex];
      const middleX = (source.x + target.x) / 2;
      const middleY = (source.y + target.y) / 2;
      const stroke = cut ? "#37d4f5" : "#405271";
      const label = cut ? "#37d4f5" : "#9ba9c2";
      return `<g>
        <line x1="${source.x}" y1="${source.y}" x2="${target.x}" y2="${target.y}" stroke="${stroke}" stroke-width="${cut ? 4 : 2}" stroke-opacity="${cut ? .95 : .72}" />
        <circle cx="${middleX}" cy="${middleY}" r="11" fill="#071425" stroke="${stroke}" stroke-width="1" />
        <text x="${middleX}" y="${middleY + 4}" fill="${label}" font-size="11" font-weight="800" text-anchor="middle">${edge.weight}</text>
      </g>`;
    }).join("");
    const nodeMarkup = positions.map((node, index) => {
      const fill = assignment[index] ? "#7566ff" : "#ffc96b";
      const group = assignment[index] ? "A" : "B";
      return `<g>
        <circle cx="${node.x}" cy="${node.y}" r="27" fill="${fill}" stroke="#ffffff" stroke-width="2" />
        <text x="${node.x}" y="${node.y + 5}" fill="#071425" font-size="13" font-weight="900" text-anchor="middle">${group}</text>
        <text x="${node.x}" y="${node.y + 48}" fill="#edf3ff" font-size="13" font-weight="760" text-anchor="middle">${escapeSvgText(node.label)}</text>
      </g>`;
    }).join("");
    svg.innerHTML = `<rect width="760" height="360" rx="14" fill="#071425" />${edgeMarkup}${nodeMarkup}`;
  }

  function renderPartitions(nodes, assignment) {
    const host = document.getElementById("partitions");
    const groups = groupsForAssignment(nodes, assignment);
    host.replaceChildren();
    [
      { key: "a", title: "Küme A · mor", items: groups.a },
      { key: "b", title: "Küme B · kehribar", items: groups.b }
    ].forEach(group => {
      const card = document.createElement("section");
      card.className = `partition ${group.key}`;
      const title = document.createElement("strong");
      title.textContent = group.title;
      const chips = document.createElement("div");
      chips.className = "partition-chips";
      group.items.forEach(item => {
        const chip = document.createElement("span");
        chip.className = "partition-chip";
        chip.textContent = item;
        chips.appendChild(chip);
      });
      card.append(title, chips);
      host.appendChild(card);
    });
  }

  function renderMaxCutMethods(results) {
    const host = document.getElementById("maxcut-methods");
    host.replaceChildren();
    results.forEach(result => {
      const card = document.createElement("div");
      card.className = `method ${result.cls}`;
      const title = document.createElement("strong");
      title.textContent = result.name;
      const score = document.createElement("small");
      score.textContent = `${result.score} kesim skoru · ${result.ms.toFixed(2)} ms`;
      const detail = document.createElement("small");
      detail.textContent = result.detail;
      card.append(title, score, detail);
      host.appendChild(card);
    });
  }

  function renderCutEdges(nodes, edges, assignment) {
    const host = document.getElementById("cut-edges");
    const cutEdges = edges
      .filter(edge => assignment[edge.sourceIndex] !== assignment[edge.targetIndex])
      .sort((first, second) => second.weight - first.weight);
    host.replaceChildren();
    if (!cutEdges.length) return;
    cutEdges.forEach(edge => {
      const row = document.createElement("div");
      row.className = "cut-edge";
      const label = document.createElement("span");
      label.textContent = `${nodes[edge.sourceIndex].label} ↔ ${nodes[edge.targetIndex].label}`;
      const score = document.createElement("strong");
      score.textContent = `+${edge.weight}`;
      row.append(label, score);
      host.appendChild(row);
    });
  }

  const maxCutButton = document.getElementById("solve-maxcut");
  maxCutButton.addEventListener("click", () => {
    const status = document.getElementById("maxcut-status");
    const nodes = maxCutNodesFromText(document.getElementById("maxcut-problem").value);
    if (nodes.length < 3) {
      status.style.color = "var(--red)";
      status.textContent = "En az üç tanınan iş adı yazmalısın: Ödeme, Kargo, İade, Teslimat veya Kampanya.";
      return;
    }
    const edges = createMaxCutGraph(nodes);
    if (!edges.length) {
      status.style.color = "var(--red)";
      status.textContent = "Seçilen işlerde görünür bir bağımlılık bulunamadı.";
      return;
    }

    maxCutButton.disabled = true;
    try {
      const results = [
        exactMaxCut(nodes, edges),
        annealMaxCut(nodes, edges),
        quantumMaxCutModel(nodes, edges)
      ];
      const best = results.reduce((first, second) => first.score >= second.score ? first : second);
      const cutCount = edges.filter(edge => best.assignment[edge.sourceIndex] !== best.assignment[edge.targetIndex]).length;
      document.getElementById("maxcut-title").textContent = `${nodes.length} iş düğümü, ${edges.length} görünür bağımlılık`;
      document.getElementById("cut-score").textContent = best.score.toLocaleString("tr-TR");
      document.getElementById("cut-count").textContent = `${cutCount} / ${edges.length}`;
      document.getElementById("cut-method").textContent = best.name;
      document.getElementById("cut-state-space").textContent = results[0].states.toLocaleString("tr-TR");
      document.getElementById("network-source").textContent = "Tarayıcı içi, açık ağırlıklı Max-Cut hesabı · Turkuaz çizgiler iki farklı kümeye taşınan bağlantıları, üzerlerindeki sayı ise bağımlılık gücünü gösterir.";
      drawNetwork(nodes, edges, best.assignment);
      renderPartitions(nodes, best.assignment);
      renderMaxCutMethods(results);
      renderCutEdges(nodes, edges, best.assignment);
      status.style.color = "var(--green)";
      status.textContent = `${nodes.length} düğüm ve ${edges.length} bağımlılık için üç yöntem aynı problemde karşılaştırıldı.`;
    } catch (error) {
      status.style.color = "var(--red)";
      status.textContent = `Ağ bölünemedi: ${error instanceof Error ? error.message : "beklenmeyen hata"}`;
    } finally {
      maxCutButton.disabled = false;
    }
  });

  setupPlacePicker();

  const previousButton = document.getElementById("solve");
  const solveButton = previousButton.cloneNode(true);
  previousButton.replaceWith(solveButton);
  const copySummaryButton = document.getElementById("copy-summary");
  copySummaryButton.addEventListener("click", () => copyShareSummary(copySummaryButton));

  solveButton.addEventListener("click", async () => {
    const status = document.getElementById("status");
    document.getElementById("share-card").hidden = true;
    const usesSelectedStops = selectedStops.length > 0;
    let cities = usesSelectedStops ? selectedStops.slice() : parseCities(document.getElementById("problem").value);
    if (cities.length < 3) {
      status.style.color = "var(--red)";
      status.textContent = usesSelectedStops
        ? "Seçtiğin duraklarla rota oluşturmak için en az üç konum eklemelisin."
        : "En az üç tanınan şehir yazmalı veya yukarıdan üç konum seçmelisin.";
      return;
    }
    const cityNotice = cities.length > 8
      ? "Tarayıcı güvenli çalışma için ilk 8 durağı kullandı."
      : usesSelectedStops
        ? `${cities.length} seçili durak WGS84 koordinatlarıyla eşleşti.`
        : `${cities.length} şehir WGS84 şehir merkezi GPS referansıyla eşleşti.`;
    if (cities.length > 8) {
      cities = cities.slice(0, 8);
    }
    solveButton.disabled = true;
    try {
      let matrix = distanceMatrix(cities);
      let durationSeconds = null;
      let roadMode = false;
      let roadTraffic = "historical";

      if (API_BASE_URL) {
        status.style.color = "var(--cyan)";
        status.textContent = `${cityNotice} Azure Maps'ten gerçek sürüş mesafesi ve süresi alınıyor...`;
        try {
          const road = await fetchRoadMatrix(cities);
          if (road) {
            matrix = road.distanceKm;
            durationSeconds = road.durationSeconds;
            roadTraffic = road.traffic;
            roadMode = true;
            status.style.color = "var(--green)";
            status.textContent = `${cityNotice} Azure Maps gerçek sürüş matrisiyle üç motor karşılaştırıldı.`;
          }
        } catch (error) {
          const detail = error instanceof Error ? error.message : "Bilinmeyen bağlantı hatası";
          status.style.color = "var(--amber)";
          status.textContent = `${cityNotice} Gerçek yol verisi alınamadı; şeffaf şekilde kuş uçuşu yedeği kullanıldı. (${detail})`;
        }
      } else {
        status.style.color = "var(--green)";
        status.textContent = `${cityNotice} Üç motor kuş uçuşu GPS mesafesiyle çalıştırıldı.`;
      }

      const results = [exact(cities, matrix), anneal(cities, matrix), quantumModel(cities, matrix)];
      const best = results.reduce((first, second) => first.cost <= second.cost ? first : second);
      const tours = Array.from({ length: cities.length - 1 }, (_, index) => index + 1)
        .reduce((total, value) => total * value, 1);
      const renderedMap = renderMap(cities, best);
      const minutes = durationMinutes(best.route, matrix, durationSeconds);

      document.getElementById("result-title").textContent = roadMode
        ? `${cities.length} durak, ${results.length} yöntem, Azure Maps yol verisi`
        : `${cities.length} durak, ${results.length} yöntem, doğrulanabilir GPS noktaları`;
      document.getElementById("best-distance-label").textContent = roadMode
        ? "Gerçek sürüş mesafesi"
        : "Kuş uçuşu mesafe";
      document.getElementById("best-duration-label").textContent = roadMode
        ? "Tahmini sürüş süresi"
        : "Referans süre*";
      document.getElementById("best-distance").textContent = formatKm(best.cost);
      document.getElementById("best-duration").textContent = formatDuration(minutes);
      document.getElementById("best-method").textContent = best.name;
      document.getElementById("state-space").textContent = tours.toLocaleString("tr-TR");
      const locationSource = usesSelectedStops
        ? "Konum: seçilen il/ilçe idari alan referansı veya Azure Maps sonucu"
        : "Konum: WGS84 şehir merkezi referansları";
      document.getElementById("map-source").textContent = roadMode
        ? `${renderedMap ? "Harita: OpenStreetMap · " : "Harita yedek görünümü · "}${locationSource} · Hesap: Azure Maps gerçek sürüş mesafesi ve süresi (${roadTraffic} trafik) · Çizgi istasyonlar arası şematiktir.`
        : `${renderedMap ? "Harita: OpenStreetMap · " : "Harita yedek görünümü · "}${locationSource} (her nokta OpenStreetMap'te açılabilir) · Mesafe: kuş uçuşu Haversine km · Süre: ${REFERENCE_SPEED_KMH} km/sa referans hız · Gerçek sürüş ve trafik verisi değildir.`;
      renderLocations(cities, best);
      renderLegs(cities, best, matrix, durationSeconds);
      const shareSummary = buildShareSummary(cities, best, roadMode, minutes);
      showShareSummary(
        shareSummary,
        `${best.name} ile ${formatKm(best.cost)} · ${roadMode ? "Azure Maps gerçek sürüş verisi" : "WGS84 GPS + kuş uçuşu hesabı"}`
      );
      document.getElementById("methods").innerHTML = results.map(result => `
        <div class="method ${result.cls}"><strong>${escapeHtml(result.name)}</strong>
          <small>${formatKm(result.cost)} ${roadMode ? "gerçek sürüş" : "kuş uçuşu"} · ${result.ms.toFixed(2)} ms</small>
          <small>${result.route.map(index => escapeHtml(cities[index].name)).join(" → ")} → ${escapeHtml(cities[result.route[0]].name)}</small>
          ${result.detail ? `<small>${escapeHtml(result.detail)}</small>` : ""}
        </div>`).join("");
    } catch (error) {
      status.style.color = "var(--red)";
      status.textContent = `Deney tamamlanamadı: ${error instanceof Error ? error.message : "beklenmeyen hata"}`;
    } finally {
      solveButton.disabled = false;
    }
  });
})();
