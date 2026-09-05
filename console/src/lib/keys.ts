import type { ApiKeys } from "./types";

const STORAGE_KEY = "pramana.apiKeys.v1";

export const EMPTY_KEYS: ApiKeys = {
  gemini: "",
  anthropic: "",
  razorpayKeyId: "",
  razorpayKeySecret: "",
};

export function loadKeys(): ApiKeys {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...EMPTY_KEYS };
    const parsed = JSON.parse(raw) as Partial<ApiKeys>;
    return {
      gemini: parsed.gemini ?? "",
      anthropic: parsed.anthropic ?? "",
      razorpayKeyId: parsed.razorpayKeyId ?? "",
      razorpayKeySecret: parsed.razorpayKeySecret ?? "",
    };
  } catch {
    return { ...EMPTY_KEYS };
  }
}

export function saveKeys(keys: ApiKeys): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(keys));
}

export function clearKeys(): void {
  localStorage.removeItem(STORAGE_KEY);
}

export function hasAnyKey(keys: ApiKeys): boolean {
  return Boolean(
    keys.gemini || keys.anthropic || keys.razorpayKeyId || keys.razorpayKeySecret,
  );
}

export function modeLabel(keys: ApiKeys): "MOCK" | "LIVE" {
  return keys.gemini || keys.anthropic ? "LIVE" : "MOCK";
}
