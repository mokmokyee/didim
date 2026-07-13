import test from "node:test";
import assert from "node:assert/strict";
import {
  BROWSER_GEMINI_LIMITS,
  createBrowserGeminiRateGuard,
} from "../public/js/gemini-rate-guard.mjs";

class MemoryStorage {
  constructor() { this.values = new Map(); }
  getItem(key) { return this.values.get(key) || null; }
  setItem(key, value) { this.values.set(key, String(value)); }
}

const locks = {
  request: async (_name, _options, callback) => callback(),
};

test("브라우저 Gemini 제한은 프로젝트 안전 예산을 지킨다", () => {
  assert.equal(BROWSER_GEMINI_LIMITS.rpm, 13);
  assert.equal(BROWSER_GEMINI_LIMITS.tpm, 250000);
  assert.ok(BROWSER_GEMINI_LIMITS.rpd < 500);
  assert.ok(BROWSER_GEMINI_LIMITS.minimumIntervalMs >= 4700);
});

test("연속 요청은 4.7초가 지나기 전에 차단한다", async () => {
  let timestamp = Date.UTC(2026, 6, 14, 0, 0, 0);
  const guard = createBrowserGeminiRateGuard({
    storage: new MemoryStorage(),
    locks,
    now: () => timestamp,
  });
  await guard.reserve({ estimatedInputTokens: 1000, maxOutputTokens: 256 });
  await assert.rejects(
    guard.reserve({ estimatedInputTokens: 1000, maxOutputTokens: 256 }),
    (error) => error.code === "gemini_rpm_guard",
  );
  timestamp += BROWSER_GEMINI_LIMITS.minimumIntervalMs;
  await guard.reserve({ estimatedInputTokens: 1000, maxOutputTokens: 256 });
});

test("TPM 상한을 넘는 요청은 저장 전에 차단한다", async () => {
  const guard = createBrowserGeminiRateGuard({
    storage: new MemoryStorage(),
    locks,
    now: () => Date.UTC(2026, 6, 14),
  });
  await assert.rejects(
    guard.reserve({ estimatedInputTokens: 249900, maxOutputTokens: 256 }),
    (error) => error.code === "gemini_tpm_guard",
  );
});

test("브라우저 일일 안전 한도 이후 요청을 차단한다", async () => {
  let timestamp = Date.UTC(2026, 6, 14, 0, 0, 0);
  const guard = createBrowserGeminiRateGuard({
    storage: new MemoryStorage(),
    locks,
    now: () => timestamp,
  });
  for (let index = 0; index < BROWSER_GEMINI_LIMITS.rpd; index += 1) {
    await guard.reserve({ estimatedInputTokens: 1000, maxOutputTokens: 256 });
    timestamp += BROWSER_GEMINI_LIMITS.minimumIntervalMs;
  }
  await assert.rejects(
    guard.reserve({ estimatedInputTokens: 1000, maxOutputTokens: 256 }),
    (error) => error.code === "gemini_rpd_guard",
  );
});

test("한도 잠금 기능이 없는 브라우저는 안전하게 차단한다", async () => {
  const guard = createBrowserGeminiRateGuard({
    storage: new MemoryStorage(),
    locks: {},
    now: () => Date.UTC(2026, 6, 14),
  });
  await assert.rejects(
    guard.reserve({ estimatedInputTokens: 1000, maxOutputTokens: 256 }),
    (error) => error.code === "gemini_rate_guard_unavailable",
  );
});
