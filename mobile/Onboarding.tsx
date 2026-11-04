import { useCallback, useMemo, useRef, useState } from "react";
import {
  Dimensions,
  FlatList,
  NativeScrollEvent,
  NativeSyntheticEvent,
  Pressable,
  SafeAreaView,
  StyleSheet,
  Text,
  View,
} from "react-native";

const { width: SCREEN_WIDTH } = Dimensions.get("window");

const COLORS = {
  bg: "#131209",
  surface: "#1F1F1F",
  border: "#313131",
  text: "#FFFFFF",
  textDim: "#9B9B9B",
  textFaint: "#6B6B6B",
  good: "#7FD98A",
};

interface Slide {
  eyebrow: string;
  title: string;
  body: string;
  mock: React.ReactNode;
}

function getSlides(): Slide[] {
  return [
    {
      eyebrow: "Sorun",
      title: "Hangi uygulamada ne kadar yiyebilirsin, hiç net değil",
      body:
        "Trendyol Go, Yemeksepeti... her uygulamaya tek tek girip fiyat karşılaştırmak zaman alır. Bütçen aynı, sonuç her yerde farklı.",
      mock: (
        <View style={styles.mockRow}>
          <View style={[styles.mockPill, { opacity: 0.4 }]}>
            <Text style={styles.mockPillText}>Trendyol Go?</Text>
          </View>
          <View style={[styles.mockPill, { opacity: 0.4 }]}>
            <Text style={styles.mockPillText}>Yemeksepeti?</Text>
          </View>
        </View>
      ),
    },
    {
      eyebrow: "Nasıl çalışır",
      title: "Bütçeni yaz, konumunu seç",
      body: "Tek ekranda bütçeni TRY olarak gir, mahalleni veya anlık konumunu seç.",
      mock: (
        <View style={styles.mockCard}>
          <Text style={styles.mockExampleTag}>ÖRNEK, CANLI VERİ DEĞİL</Text>
          <Text style={styles.mockLabel}>Bütçe (TRY)</Text>
          <View style={styles.mockInput}>
            <Text style={styles.mockInputText}>300</Text>
          </View>
          <Text style={styles.mockLabel}>Konum</Text>
          <View style={styles.mockRow}>
            <View style={styles.mockPillStatic}>
              <Text style={styles.mockPillStaticTextActive}>Kadıköy</Text>
            </View>
            <View style={styles.mockPillStatic}>
              <Text style={styles.mockPillStaticText}>Beşiktaş</Text>
            </View>
          </View>
        </View>
      ),
    },
    {
      eyebrow: "Sonuç",
      title: "Gerçek, canlı fiyatlarla ne yiyebileceğini gör",
      body:
        "Hiçbir fiyat uydurulmaz: her sonuç, aramayı yaptığın anda Trendyol Go ve Yemeksepeti'nden gerçek zamanlı çekilir.",
      mock: (
        <View style={styles.mockCard}>
          <Text style={styles.mockExampleTag}>ÖRNEK, CANLI VERİ DEĞİL</Text>
          <View style={styles.mockResultRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.mockResultName}>Footlong Sub Menü</Text>
              <Text style={styles.mockResultSub}>Subway (Kadıköy) · 0.8 km</Text>
            </View>
            <Text style={styles.mockResultPrice}>145 TRY</Text>
          </View>
          <View style={styles.mockResultRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.mockResultName}>Whopper Menü</Text>
              <Text style={styles.mockResultSub}>Burger King · Yemeksepeti</Text>
            </View>
            <Text style={styles.mockResultPrice}>189 TRY</Text>
          </View>
        </View>
      ),
    },
  ];
}

export default function Onboarding({ onFinish }: { onFinish: () => void }) {
  const [index, setIndex] = useState(0);
  const slides = useMemo(() => getSlides(), []);
  const listRef = useRef<FlatList<Slide>>(null);

  const goTo = useCallback((next: number) => {
    setIndex(next);
    listRef.current?.scrollToOffset({ offset: next * SCREEN_WIDTH, animated: true });
  }, []);

  const handleScrollEnd = useCallback((e: NativeSyntheticEvent<NativeScrollEvent>) => {
    const next = Math.round(e.nativeEvent.contentOffset.x / SCREEN_WIDTH);
    setIndex(next);
  }, []);

  const isLast = index === slides.length - 1;

  return (
    <SafeAreaView style={styles.safeArea}>
      <FlatList
        ref={listRef}
        data={slides}
        keyExtractor={(_, i) => `slide-${i}`}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onMomentumScrollEnd={handleScrollEnd}
        style={styles.list}
        renderItem={({ item }) => (
          <View style={[styles.slide, { width: SCREEN_WIDTH }]}>
            <View>
              <Text style={styles.eyebrow}>{item.eyebrow}</Text>
              <Text style={styles.title}>{item.title}</Text>
              <Text style={styles.body}>{item.body}</Text>
            </View>
            <View style={styles.mockWrap}>{item.mock}</View>
          </View>
        )}
      />

      <View style={styles.footer}>
        <View style={styles.dotsRow}>
          {slides.map((_, i) => (
            <View key={i} style={[styles.dot, i === index && styles.dotActive]} />
          ))}
        </View>

        <View style={styles.footerButtons}>
          {!isLast ? (
            <Pressable onPress={onFinish} style={styles.skipButton}>
              <Text style={styles.skipButtonText}>Geç</Text>
            </Pressable>
          ) : (
            <View style={styles.skipButton} />
          )}
          <Pressable
            onPress={() => (isLast ? onFinish() : goTo(index + 1))}
            style={styles.primaryButton}
          >
            <Text style={styles.primaryButtonText}>{isLast ? "Başla" : "İleri"}</Text>
          </Pressable>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: COLORS.bg,
  },
  list: {
    flex: 1,
  },
  slide: {
    flex: 1,
    padding: 28,
    paddingTop: 72,
    justifyContent: "flex-start",
    gap: 40,
  },
  eyebrow: {
    color: COLORS.good,
    fontSize: 13,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 0.5,
    marginBottom: 12,
  },
  title: {
    color: COLORS.text,
    fontSize: 26,
    fontWeight: "700",
    lineHeight: 32,
    marginBottom: 14,
  },
  body: {
    color: COLORS.textDim,
    fontSize: 15,
    lineHeight: 21,
  },
  mockWrap: {
    marginTop: 4,
  },
  mockCard: {
    backgroundColor: COLORS.surface,
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: 16,
    padding: 18,
    gap: 6,
  },
  mockExampleTag: {
    color: COLORS.textFaint,
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 0.5,
    marginBottom: 6,
  },
  mockLabel: {
    color: COLORS.textDim,
    fontSize: 12,
    fontWeight: "600",
    marginTop: 10,
    marginBottom: 6,
  },
  mockInput: {
    backgroundColor: COLORS.bg,
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 12,
  },
  mockInputText: {
    color: COLORS.text,
    fontSize: 16,
  },
  mockRow: {
    flexDirection: "row",
    gap: 8,
    flexWrap: "wrap",
  },
  mockPill: {
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: 999,
    paddingVertical: 8,
    paddingHorizontal: 12,
  },
  mockPillText: {
    color: COLORS.textDim,
    fontSize: 13,
    fontWeight: "600",
  },
  // Deliberately styled flatter than the real app's Pressable chips (no solid
  // white "active" fill) so this illustration doesn't read as a tappable
  // control -- confirmed live 2026-11-04 the owner tried tapping these.
  mockPillStatic: {
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: 999,
    paddingVertical: 8,
    paddingHorizontal: 12,
    opacity: 0.7,
  },
  mockPillStaticText: {
    color: COLORS.textDim,
    fontSize: 13,
    fontWeight: "600",
  },
  mockPillStaticTextActive: {
    color: COLORS.good,
    fontSize: 13,
    fontWeight: "600",
  },
  mockResultRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
    paddingVertical: 10,
  },
  mockResultName: {
    color: COLORS.text,
    fontSize: 14,
    fontWeight: "600",
  },
  mockResultSub: {
    color: COLORS.textDim,
    fontSize: 12,
    marginTop: 2,
  },
  mockResultPrice: {
    color: COLORS.good,
    fontSize: 15,
    fontWeight: "700",
  },
  footer: {
    padding: 24,
    paddingTop: 12,
  },
  dotsRow: {
    flexDirection: "row",
    justifyContent: "center",
    gap: 6,
    marginBottom: 20,
  },
  dot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: COLORS.border,
  },
  dotActive: {
    backgroundColor: COLORS.good,
    width: 18,
  },
  footerButtons: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  skipButton: {
    paddingVertical: 12,
    paddingHorizontal: 16,
    minWidth: 60,
  },
  skipButtonText: {
    color: COLORS.textDim,
    fontSize: 14,
    fontWeight: "600",
  },
  primaryButton: {
    backgroundColor: COLORS.text,
    borderRadius: 10,
    paddingVertical: 13,
    paddingHorizontal: 28,
  },
  primaryButtonText: {
    color: COLORS.bg,
    fontSize: 16,
    fontWeight: "700",
  },
});
