/* Conservative browser-side guard for the shared Gemini free-tier key. */
export const BROWSER_GEMINI_LIMITS = Object.freeze({
  rpm: 1,
  tpm: 250000,
  rpd: 400,
  minimumIntervalMs: 61000,
  maxOutputTokens: 256,
});

const STORAGE_KEY = "didim:gemini-rate-guard:v1";
const LOCK_NAME = "didim-gemini-rate-guard";

function quotaError(message, code, status, retryAfterSeconds) {
  const error = new Error(message);
  error.code = code;
  error.status = status;
  if (retryAfterSeconds) error.retryAfterSeconds = retryAfterSeconds;
  return error;
}

function quotaDate(timestamp) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Los_Angeles",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(timestamp));
  const values = Object.fromEntries(parts.map(function (part) { return [part.type, part.value]; }));
  return values.year + "-" + values.month + "-" + values.day;
}

function readState(storage, today) {
  let parsed = {};
  try {
    parsed = JSON.parse(storage.getItem(STORAGE_KEY) || "{}");
  } catch (_error) {
    parsed = {};
  }
  if (parsed.day !== today) return { day: today, dayCount: 0, lastReservedAt: 0 };
  return {
    day: today,
    dayCount: Math.max(0, Number(parsed.dayCount || 0)),
    lastReservedAt: Math.max(0, Number(parsed.lastReservedAt || 0)),
  };
}

export function createBrowserGeminiRateGuard(options = {}) {
  const storage = options.storage || globalThis.localStorage;
  const locks = options.locks || (globalThis.navigator && globalThis.navigator.locks);
  const now = options.now || Date.now;

  async function reserve({ estimatedInputTokens, maxOutputTokens }) {
    const estimatedTotalTokens = Math.max(0, Number(estimatedInputTokens || 0)) +
      Math.max(0, Number(maxOutputTokens || 0));
    if (estimatedTotalTokens > BROWSER_GEMINI_LIMITS.tpm) {
      throw quotaError(
        "검색 요청이 무료 TPM 안전 한도를 초과해 차단됐습니다.",
        "gemini_tpm_guard",
        413,
      );
    }
    if (!storage || !locks || typeof locks.request !== "function") {
      throw quotaError(
        "이 브라우저에서는 Gemini 무료 한도 보호 기능을 사용할 수 없어 AI 검색을 차단했습니다.",
        "gemini_rate_guard_unavailable",
        503,
      );
    }

    return locks.request(LOCK_NAME, { mode: "exclusive" }, async function () {
      const timestamp = Number(now());
      const today = quotaDate(timestamp);
      const state = readState(storage, today);
      const elapsed = timestamp - state.lastReservedAt;
      if (state.lastReservedAt && elapsed < BROWSER_GEMINI_LIMITS.minimumIntervalMs) {
        const waitSeconds = Math.ceil((BROWSER_GEMINI_LIMITS.minimumIntervalMs - elapsed) / 1000);
        throw quotaError(
          "AI 검색은 무료 한도 보호를 위해 1분에 한 번만 사용할 수 있어요. " + waitSeconds + "초 후 다시 시도해 주세요.",
          "gemini_rpm_guard",
          429,
          waitSeconds,
        );
      }
      if (state.dayCount >= BROWSER_GEMINI_LIMITS.rpd) {
        throw quotaError(
          "오늘의 AI 검색 안전 한도에 도달했습니다. 내일 다시 이용해 주세요.",
          "gemini_rpd_guard",
          429,
        );
      }

      const next = {
        day: today,
        dayCount: state.dayCount + 1,
        lastReservedAt: timestamp,
      };
      try {
        storage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch (_error) {
        throw quotaError(
          "Gemini 무료 한도를 안전하게 기록할 수 없어 AI 검색을 차단했습니다.",
          "gemini_rate_guard_unavailable",
          503,
        );
      }
      return next;
    });
  }

  return { reserve };
}
