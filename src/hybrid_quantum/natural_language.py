from __future__ import annotations

import json
import os
import unicodedata
from dataclasses import dataclass

from dotenv import load_dotenv
from openai import AzureOpenAI

from .models import City


load_dotenv()


# Eğitim demosu için WGS84 şehir merkezi referans koordinatları kullanılır; yol mesafesi değildir.
# Bu liste, yayımlanan web demosundaki GPS_CITIES kataloğuyla eşit tutulur.
CITY_CATALOG: dict[str, tuple[str, float, float]] = {
    "istanbul": ("İstanbul", 28.9784, 41.0082),
    "ankara": ("Ankara", 32.8597, 39.9334),
    "izmir": ("İzmir", 27.1428, 38.4237),
    "antalya": ("Antalya", 30.7133, 36.8969),
    "bursa": ("Bursa", 29.0600, 40.1950),
    "konya": ("Konya", 32.4846, 37.8714),
    "adana": ("Adana", 35.3213, 37.0000),
    "gaziantep": ("Gaziantep", 37.3833, 37.0662),
    "trabzon": ("Trabzon", 39.7178, 41.0015),
    "samsun": ("Samsun", 36.3300, 41.2867),
    "kayseri": ("Kayseri", 35.4875, 38.7225),
    "diyarbakir": ("Diyarbakır", 40.2306, 37.9144),
    "elazig": ("Elazığ", 39.2264, 38.6810),
    "eskisehir": ("Eskişehir", 30.5256, 39.7667),
}


@dataclass(frozen=True)
class ParsedRouteProblem:
    cities: list[City]
    use_quantum: bool
    parser_source: str

    @property
    def summary(self) -> str:
        route_names = ", ".join(city.name for city in self.cities)
        quantum_text = "kuantum karşılaştırması açık" if self.use_quantum else "standart karşılaştırma"
        return f"{len(self.cities)} şehir: {route_names} · hedef: en kısa kapalı tur · {quantum_text}"


def _normalize(value: str) -> str:
    lowered = value.casefold().replace("ı", "i")
    decomposed = unicodedata.normalize("NFKD", lowered)
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def _local_city_keys(text: str) -> list[str]:
    normalized = _normalize(text)
    positions = [
        (normalized.find(city_key), city_key)
        for city_key in CITY_CATALOG
        if normalized.find(city_key) >= 0
    ]
    return [city_key for _, city_key in sorted(positions)]


def _azure_city_keys(text: str) -> list[str] | None:
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    if not all((endpoint, api_key, deployment)):
        return None

    allowed = list(CITY_CATALOG)
    client = AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
    )
    try:
        response = client.chat.completions.create(
            model=deployment,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Kullanıcının Türkçe rota isteğinden şehirleri geçiş sırasıyla çıkar. "
                        "Yalnızca izin verilen şehir anahtarlarını kullan. JSON biçimi: "
                        '{"cities":["istanbul","ankara"],"use_quantum":true}. '
                        f"İzin verilen şehirler: {allowed}. Tahmin etme ve ek alan üretme."
                    ),
                },
                {"role": "user", "content": text},
            ],
            temperature=0,
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        keys = [str(key) for key in parsed.get("cities", []) if str(key) in CITY_CATALOG]
        return list(dict.fromkeys(keys))
    except Exception:
        return None


def parse_route_problem(text: str) -> ParsedRouteProblem:
    if not text.strip():
        raise ValueError("Önce çözmek istediğiniz rota problemini bir cümleyle yazın.")

    azure_keys = _azure_city_keys(text)
    city_keys = azure_keys or _local_city_keys(text)
    parser_source = "Azure OpenAI" if azure_keys else "Yerel şehir sözlüğü"
    if len(city_keys) < 3:
        supported = ", ".join(city[0] for city in CITY_CATALOG.values())
        raise ValueError(
            "En az 3 desteklenen şehir yazın. Şimdilik kullanılabilen şehirler: " + supported
        )

    cities = [
        City(name=CITY_CATALOG[key][0], x=CITY_CATALOG[key][1], y=CITY_CATALOG[key][2])
        for key in city_keys[:10]
    ]
    normalized = _normalize(text)
    use_quantum = any(token in normalized for token in ("kuantum", "quantum", "q#", "qsharp"))
    return ParsedRouteProblem(
        cities=cities,
        use_quantum=use_quantum,
        parser_source=parser_source,
    )
