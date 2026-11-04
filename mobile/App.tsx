// Ucuz Yemek -- native client.
//
// This is deliberately a THIN CLIENT over the Ucuz Yemek backend (same
// FastAPI app the web frontend talks to) -- no business logic, no local
// matching/ranking, no mock data. Every search result on screen is a live
// fetch made at request time, same as the web version. See lib/api.ts for
// the current host status (as of 2026-11-04 it's down) and
// ~/products/plans/ucuz-yemek.md for the open item on where this should
// point next.
import { StatusBar } from "expo-status-bar";
import * as Location from "expo-location";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Platform,
  Pressable,
  SafeAreaView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import {
  AffordableItem,
  ApiError,
  City,
  SortMode,
  fetchCities,
  isServiceUnavailable,
  nearestCity,
  platformLabel,
  searchBudget,
  searchCityBudget,
} from "./lib/api";
import { FALLBACK_CITY_SLUG } from "./lib/locations";
import Onboarding from "./Onboarding";
import { hasSeenOnboarding, markOnboardingSeen } from "./lib/onboarding";

const COLORS = {
  bg: "#131209",
  surface: "#1F1F1F",
  surface2: "#272727",
  border: "#313131",
  text: "#FFFFFF",
  textDim: "#9B9B9B",
  textFaint: "#6B6B6B",
  good: "#7FD98A",
  warn: "#E5C07B",
  error: "#E5A3A3",
};

const SORT_OPTIONS: { value: SortMode; label: string }[] = [
  { value: "best_value", label: "En iyi değer" },
  { value: "closest_to_budget", label: "Bütçeye en yakın" },
  { value: "cheapest_first", label: "Önce ucuz" },
  { value: "priciest_first", label: "Önce pahalı" },
];

interface NormalizedResult {
  items: AffordableItem[];
  platform_errors: Record<string, string> | null;
}

type SearchState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "success"; data: NormalizedResult };

export default function App() {
  const [budget, setBudget] = useState("300");
  const [query, setQuery] = useState("");
  const [cities, setCities] = useState<City[]>([]);
  const [selectedCitySlug, setSelectedCitySlug] = useState<string>(FALLBACK_CITY_SLUG);
  const [sort, setSort] = useState<SortMode>("best_value");
  const [customCoords, setCustomCoords] = useState<{ lat: number; lon: number } | null>(
    null
  );
  const [locatingDevice, setLocatingDevice] = useState(false);
  const [state, setState] = useState<SearchState>({ status: "idle" });
  const [showOnboarding, setShowOnboarding] = useState<boolean | null>(null);
  const [backendUnavailable, setBackendUnavailable] = useState(false);

  useEffect(() => {
    hasSeenOnboarding().then((seen) => setShowOnboarding(!seen));
  }, []);

  useEffect(() => {
    fetchCities()
      .then((list) => {
        setCities(list);
        setBackendUnavailable(false);
      })
      .catch((err) => {
        // Real city list unavailable. The FALLBACK_CITY_SLUG default still
        // lets city-based search work once the backend is reachable again,
        // but surface this honestly instead of pretending nothing is wrong --
        // the user is about to tap "search" against a backend we already
        // know just failed.
        setBackendUnavailable(isServiceUnavailable(err));
      });
  }, []);

  const finishOnboarding = useCallback(() => {
    setShowOnboarding(false);
    markOnboardingSeen();
  }, []);

  const activeCity = useMemo(
    () => cities.find((c) => c.slug === selectedCitySlug) ?? null,
    [cities, selectedCitySlug]
  );

  const nearestCityToDevice = useMemo(
    () => (customCoords ? nearestCity(customCoords.lat, customCoords.lon, cities) : null),
    [customCoords, cities]
  );

  const activeLocationLabel = customCoords
    ? `Cihaz konumum${nearestCityToDevice ? ` (en yakın: ${nearestCityToDevice.display_name})` : ""}`
    : activeCity?.display_name ?? "İstanbul";

  const useDeviceLocation = useCallback(async () => {
    setLocatingDevice(true);
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== "granted") {
        setState({
          status: "error",
          message: "Location permission denied. Pick a city instead.",
        });
        return;
      }
      const position = await Location.getCurrentPositionAsync({});
      const lat = position.coords.latitude;
      const lon = position.coords.longitude;
      setCustomCoords({ lat, lon });
      const nearest = nearestCity(lat, lon, cities);
      if (nearest) setSelectedCitySlug(nearest.slug);
    } catch {
      setState({
        status: "error",
        message: "Could not read device location. Pick a city instead.",
      });
    } finally {
      setLocatingDevice(false);
    }
  }, [cities]);

  const pickCity = useCallback((slug: string) => {
    setCustomCoords(null);
    setSelectedCitySlug(slug);
  }, []);

  const runSearch = useCallback(async () => {
    const parsedBudget = parseFloat(budget);
    if (!parsedBudget || parsedBudget <= 0) {
      setState({ status: "error", message: "Enter a budget greater than 0." });
      return;
    }

    setState({ status: "loading" });
    try {
      const result: NormalizedResult = customCoords
        ? await searchBudget({
            budget: parsedBudget,
            lat: customCoords.lat,
            lon: customCoords.lon,
            sort,
            limit: 30,
            q: query.trim() || undefined,
          })
        : await searchCityBudget({
            citySlug: selectedCitySlug,
            budget: parsedBudget,
            sort,
            limit: 30,
            q: query.trim() || undefined,
          });
      setState({ status: "success", data: result });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Unknown error.";
      setState({ status: "error", message });
    }
  }, [budget, query, customCoords, selectedCitySlug, sort]);

  if (showOnboarding === null) {
    return <SafeAreaView style={styles.safeArea} />;
  }

  if (showOnboarding) {
    return <Onboarding onFinish={finishOnboarding} />;
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar style="light" />
      <FlatList
        data={state.status === "success" ? state.data.items : []}
        keyExtractor={(item, idx) => `${item.platform}-${item.restaurant_name}-${item.item_name}-${idx}`}
        contentContainerStyle={styles.listContent}
        ListHeaderComponent={
          <View>
            {backendUnavailable ? <BackendUnavailableBanner /> : null}
            <Header
              budget={budget}
              onBudgetChange={setBudget}
              query={query}
              onQueryChange={setQuery}
              cities={cities}
              selectedCitySlug={selectedCitySlug}
              onPickCity={pickCity}
              usingDeviceLocation={!!customCoords}
              locatingDevice={locatingDevice}
              onUseDeviceLocation={useDeviceLocation}
              sort={sort}
              onSortChange={setSort}
              onSubmit={runSearch}
              loading={state.status === "loading"}
              activeLocationLabel={activeLocationLabel}
            />
          </View>
        }
        ListFooterComponent={
          state.status === "success" ? (
            <Text style={styles.footerNote}>
              Source code: github.com/caelum0x/ucuz-yemek -- every number above is a live
              fetch made at request time, nothing cached or fabricated.
            </Text>
          ) : undefined
        }
        renderItem={({ item }) => <ResultRow item={item} />}
        ListEmptyComponent={<ResultsEmptyState state={state} />}
      />
    </SafeAreaView>
  );
}

function Header(props: {
  budget: string;
  onBudgetChange: (v: string) => void;
  query: string;
  onQueryChange: (v: string) => void;
  cities: City[];
  selectedCitySlug: string;
  onPickCity: (slug: string) => void;
  usingDeviceLocation: boolean;
  locatingDevice: boolean;
  onUseDeviceLocation: () => void;
  sort: SortMode;
  onSortChange: (s: SortMode) => void;
  onSubmit: () => void;
  loading: boolean;
  activeLocationLabel: string;
}) {
  return (
    <View>
      <Text style={styles.title}>Bu bütçeyle ne yiyebilirim?</Text>
      <Text style={styles.subtitle}>
        Bütçeni TRY olarak gir, konumunu seç. Trendyol Go ve Yemeksepeti üzerindeki gerçek,
        canlı fiyatlarla şu an yiyebileceğin şeyleri gör.
      </Text>

      <View style={styles.card}>
        <Text style={styles.label}>Bütçe (TRY)</Text>
        <TextInput
          value={props.budget}
          onChangeText={props.onBudgetChange}
          keyboardType="numeric"
          placeholder="300"
          placeholderTextColor={COLORS.textFaint}
          style={styles.input}
        />

        <Text style={styles.label}>Ara (opsiyonel)</Text>
        <TextInput
          value={props.query}
          onChangeText={props.onQueryChange}
          placeholder="örn. burger, subway, döner"
          placeholderTextColor={COLORS.textFaint}
          style={styles.input}
          autoCapitalize="none"
          autoCorrect={false}
        />

        <Text style={styles.label}>Şehir ({props.cities.length || 20} gerçek şehir)</Text>
        <View style={styles.chipRow}>
          {props.cities.map((city) => {
            const active = city.slug === props.selectedCitySlug && !props.usingDeviceLocation;
            return (
              <Pressable
                key={city.slug}
                onPress={() => props.onPickCity(city.slug)}
                style={[styles.chip, active && styles.chipActive]}
              >
                <Text style={[styles.chipText, active && styles.chipTextActive]}>
                  {city.display_name}
                </Text>
              </Pressable>
            );
          })}
          <Pressable
            onPress={props.onUseDeviceLocation}
            style={[styles.chip, props.usingDeviceLocation && styles.chipActive]}
          >
            {props.locatingDevice ? (
              <ActivityIndicator size="small" color={COLORS.text} />
            ) : (
              <Text
                style={[styles.chipText, props.usingDeviceLocation && styles.chipTextActive]}
              >
                Konumumu kullan
              </Text>
            )}
          </Pressable>
        </View>
        <Text style={styles.scopeNote}>Seçili: {props.activeLocationLabel}</Text>

        <Text style={styles.label}>Sırala</Text>
        <View style={styles.chipRow}>
          {SORT_OPTIONS.map((opt) => {
            const active = opt.value === props.sort;
            return (
              <Pressable
                key={opt.value}
                onPress={() => props.onSortChange(opt.value)}
                style={[styles.chip, active && styles.chipActive]}
              >
                <Text style={[styles.chipText, active && styles.chipTextActive]}>
                  {opt.label}
                </Text>
              </Pressable>
            );
          })}
        </View>

        <Pressable
          onPress={props.onSubmit}
          disabled={props.loading}
          style={[styles.submitButton, props.loading && styles.submitButtonDisabled]}
        >
          {props.loading ? (
            <ActivityIndicator size="small" color={COLORS.bg} />
          ) : (
            <Text style={styles.submitButtonText}>Ne yiyebilirim, göster</Text>
          )}
        </Pressable>

        <Text style={styles.scopeNote}>
          Trendyol Go: konuma en yakın gerçek restoranlar, gerçek mesafeye göre sıralanır.
          Yemeksepeti: popüler zincirlerden seçilmiş bir liste (bu platformda henüz gerçek bir
          konum arama API&apos;si yok).
        </Text>
      </View>
    </View>
  );
}

function ResultsEmptyState({ state }: { state: SearchState }) {
  if (state.status === "idle") {
    return (
      <Text style={styles.emptyHint}>
        Bütçeni ve konumunu seç, sonra &quot;Ne yiyebilirim, göster&quot;e dokun.
      </Text>
    );
  }
  if (state.status === "loading") {
    return (
      <View style={styles.emptyHint}>
        <ActivityIndicator color={COLORS.text} />
      </View>
    );
  }
  if (state.status === "error") {
    return (
      <View style={[styles.stateBox, styles.stateBoxError]}>
        <Text style={styles.stateBoxErrorText}>Arama başarısız oldu. {state.message}</Text>
      </View>
    );
  }
  if (state.status === "success" && state.data.items.length === 0) {
    return (
      <View>
        <PlatformWarning errors={state.data.platform_errors} />
        <View style={styles.stateBox}>
          <Text style={styles.stateBoxText}>
            Bu bütçe ve konum için şu an uygun fiyatlı gerçek bir ürün bulunamadı. Daha yüksek
            bir bütçe veya farklı bir konum dene.
          </Text>
        </View>
      </View>
    );
  }
  return null;
}

function BackendUnavailableBanner() {
  return (
    <View style={[styles.stateBox, styles.stateBoxWarning]}>
      <Text style={styles.stateBoxWarningText}>
        Ucuz Yemek sunucusuna şu anda ulaşılamıyor. Arama şimdilik çalışmayabilir, lütfen daha
        sonra tekrar dene.
      </Text>
    </View>
  );
}

function PlatformWarning({ errors }: { errors: Record<string, string> | null }) {
  const names = errors ? Object.keys(errors) : [];
  if (names.length === 0) return null;
  const label = names.map((n) => platformLabel(n as any)).join(" ve ");
  return (
    <View style={[styles.stateBox, styles.stateBoxWarning]}>
      <Text style={styles.stateBoxWarningText}>
        {label} şu anda geçici olarak erişilemiyor, aşağıdaki sonuçlar sadece diğer platformdan
        (hiçbir veri uydurulmadı).
      </Text>
    </View>
  );
}

function ResultRow({ item }: { item: AffordableItem }) {
  const meta: string[] = [];
  if (item.distance_km != null) meta.push(`${item.distance_km.toFixed(1)} km`);
  if (item.rating != null) meta.push(`${item.rating.toFixed(1)}★`);

  return (
    <View style={styles.resultRow}>
      <View style={styles.resultInfo}>
        <Text style={styles.resultName} numberOfLines={1}>
          {item.item_name}
        </Text>
        <Text style={styles.resultRestaurant} numberOfLines={1}>
          {item.restaurant_name}
        </Text>
        {meta.length > 0 ? <Text style={styles.resultMeta}>{meta.join(" · ")}</Text> : null}
      </View>
      <View style={styles.resultPriceWrap}>
        <Text style={styles.platformTag}>{platformLabel(item.platform)}</Text>
        <Text style={styles.resultPrice}>{item.price_try} TRY</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: COLORS.bg,
    paddingTop: Platform.OS === "android" ? 24 : 0,
  },
  listContent: {
    padding: 20,
    paddingBottom: 48,
  },
  title: {
    color: COLORS.text,
    fontSize: 28,
    fontWeight: "700",
    marginBottom: 6,
  },
  subtitle: {
    color: COLORS.textDim,
    fontSize: 15,
    lineHeight: 21,
    marginBottom: 20,
  },
  card: {
    backgroundColor: COLORS.surface,
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: 16,
    padding: 18,
    marginBottom: 20,
    gap: 4,
  },
  label: {
    color: COLORS.textDim,
    fontSize: 13,
    fontWeight: "600",
    marginTop: 12,
    marginBottom: 8,
  },
  input: {
    backgroundColor: COLORS.bg,
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: 10,
    color: COLORS.text,
    fontSize: 16,
    paddingVertical: 10,
    paddingHorizontal: 12,
  },
  chipRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  chip: {
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: 999,
    paddingVertical: 8,
    paddingHorizontal: 12,
    minHeight: 36,
    justifyContent: "center",
  },
  chipActive: {
    backgroundColor: COLORS.text,
    borderColor: COLORS.text,
  },
  chipText: {
    color: COLORS.textDim,
    fontSize: 13,
    fontWeight: "600",
  },
  chipTextActive: {
    color: COLORS.bg,
  },
  scopeNote: {
    color: COLORS.textFaint,
    fontSize: 12,
    marginTop: 8,
    lineHeight: 16,
  },
  submitButton: {
    backgroundColor: COLORS.text,
    borderRadius: 10,
    paddingVertical: 13,
    alignItems: "center",
    marginTop: 16,
  },
  submitButtonDisabled: {
    opacity: 0.6,
  },
  submitButtonText: {
    color: COLORS.bg,
    fontSize: 16,
    fontWeight: "700",
  },
  emptyHint: {
    color: COLORS.textDim,
    fontSize: 14,
    textAlign: "center",
    marginTop: 24,
  },
  stateBox: {
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: 12,
    padding: 18,
  },
  stateBoxText: {
    color: COLORS.textDim,
    fontSize: 14,
  },
  stateBoxError: {
    borderColor: "#4A2A2A",
  },
  stateBoxErrorText: {
    color: COLORS.error,
    fontSize: 14,
  },
  stateBoxWarning: {
    borderColor: "#4A3A1A",
    marginBottom: 10,
  },
  stateBoxWarningText: {
    color: COLORS.warn,
    fontSize: 13,
  },
  resultRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: COLORS.surface,
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: 12,
    padding: 14,
    marginBottom: 8,
    gap: 12,
  },
  resultInfo: {
    flex: 1,
    gap: 2,
  },
  resultName: {
    color: COLORS.text,
    fontSize: 15,
    fontWeight: "600",
  },
  resultRestaurant: {
    color: COLORS.textDim,
    fontSize: 13,
  },
  resultMeta: {
    color: COLORS.textDim,
    fontSize: 12,
    opacity: 0.8,
  },
  resultPriceWrap: {
    alignItems: "flex-end",
    gap: 4,
  },
  platformTag: {
    color: COLORS.textDim,
    fontSize: 10,
    fontWeight: "700",
    textTransform: "uppercase",
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: 999,
    paddingVertical: 2,
    paddingHorizontal: 8,
  },
  resultPrice: {
    color: COLORS.good,
    fontSize: 16,
    fontWeight: "700",
  },
  footerNote: {
    color: COLORS.textFaint,
    fontSize: 12,
    marginTop: 24,
    lineHeight: 16,
  },
});
