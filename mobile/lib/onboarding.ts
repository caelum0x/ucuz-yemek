import AsyncStorage from "@react-native-async-storage/async-storage";

const ONBOARDING_SEEN_KEY = "ucuz_yemek_onboarding_v1_seen";

export async function hasSeenOnboarding(): Promise<boolean> {
  try {
    return (await AsyncStorage.getItem(ONBOARDING_SEEN_KEY)) === "true";
  } catch {
    return false;
  }
}

export async function markOnboardingSeen(): Promise<void> {
  try {
    await AsyncStorage.setItem(ONBOARDING_SEEN_KEY, "true");
  } catch {
    // Non-fatal: worst case the user sees onboarding again next launch.
  }
}
