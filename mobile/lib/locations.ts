// Same preset districts as the web frontend (web/index.html) for parity --
// real Istanbul coordinates, not placeholders.
export interface PresetLocation {
  label: string;
  lat: number;
  lon: number;
}

export const PRESET_LOCATIONS: PresetLocation[] = [
  { label: "Beşiktaş, İstanbul", lat: 41.0422, lon: 29.0061 },
  { label: "Kadıköy, İstanbul", lat: 40.9833, lon: 29.0333 },
  { label: "Şişli, İstanbul", lat: 41.0766, lon: 29.0577 },
  { label: "Ataşehir, İstanbul", lat: 40.9923, lon: 29.1244 },
];
