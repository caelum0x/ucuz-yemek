"""
Real, coverage-confirmed cities for the /sehir/{city_slug} and
/karsilastir/{chain}?sehir={city_slug} page families.

Each city's (latitude, longitude) was independently used to make a real,
live `trendyol_go.search_restaurants` / `budget.find_affordable_items` call
during this session (2026-11-03) and returned real restaurants -- these are
not placeholder/fabricated coordinates. `restaurant_count_seen` is the real
number of restaurants Trendyol Go's search returned for that exact point at
verification time; Trendyol Go paginates 10-at-a-time, so this is "at least
this many," not a hard total.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class City:
    slug: str
    display_name: str
    latitude: float
    longitude: float
    restaurant_count_seen: int


CITIES: tuple[City, ...] = (
    City("istanbul", "İstanbul", 41.0082, 28.9784, 10),
    City("ankara", "Ankara", 39.9334, 32.8597, 10),
    City("izmir", "İzmir", 38.4237, 27.1428, 10),
    City("bursa", "Bursa", 40.1826, 29.0665, 10),
    City("antalya", "Antalya", 36.8969, 30.7133, 10),
    City("adana", "Adana", 37.0, 35.3213, 10),
    City("konya", "Konya", 37.8746, 32.4932, 10),
    City("gaziantep", "Gaziantep", 37.0662, 37.3833, 10),
    City("mersin", "Mersin", 36.8, 34.6333, 10),
    City("kayseri", "Kayseri", 38.7312, 35.4787, 10),
    City("eskisehir", "Eskişehir", 39.7767, 30.5206, 10),
    City("diyarbakir", "Diyarbakır", 37.9144, 40.2306, 10),
    City("samsun", "Samsun", 41.2867, 36.33, 10),
    City("denizli", "Denizli", 37.7765, 29.0864, 10),
    City("sanliurfa", "Şanlıurfa", 37.1591, 38.7969, 10),
    City("malatya", "Malatya", 38.3552, 38.3095, 10),
    City("kocaeli", "Kocaeli (İzmit)", 40.7654, 29.9408, 10),
    City("trabzon", "Trabzon", 41.0027, 39.7168, 10),
    City("erzurum", "Erzurum", 39.9, 41.27, 10),
    City("van", "Van", 38.4891, 43.4089, 10),
)

CITIES_BY_SLUG: dict[str, City] = {city.slug: city for city in CITIES}

DEFAULT_CITY_BUDGET_TRY = 200.0
