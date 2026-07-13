/* DiDim opportunity target normalization and fallback inference. */
const ALL_AGES = "전 연령";
const HIGH_SCHOOL = "고등학생";
const COLLEGE = "대학생";

const TARGET_ALIASES = Object.freeze({
  [ALL_AGES]: ["전 연령", "전연령", "누구나", "연령 무관", "나이 무관", "연령 제한 없음"],
  [HIGH_SCHOOL]: ["고등학생", "고교생"],
  [COLLEGE]: ["대학생", "학부생", "전문대생"],
});

const TEXT_FIELDS = Object.freeze([
  "title",
  "raw_title",
  "category",
  "program_introduction",
  "summary",
  "description",
  "activity_content",
  "eligibility",
  "requirements",
  "age_requirement",
  "ageRequirement",
  "raw_text",
]);

function normalizeText(value) {
  return String(value || "").normalize("NFKC").replace(/\s+/g, " ").trim();
}

function normalizeLookup(value) {
  return normalizeText(value).toLocaleLowerCase("ko-KR").replace(/[\s·._\-/]+/g, "");
}

function asArray(value) {
  if (Array.isArray(value)) return value;
  if (value === undefined || value === null || value === "") return [];
  return [value];
}

const exactTargetAliases = new Map();
Object.entries(TARGET_ALIASES).forEach(function ([target, aliases]) {
  [target].concat(aliases).forEach(function (alias) {
    exactTargetAliases.set(normalizeLookup(alias), target);
  });
});

export function normalizeExplicitTargets(value) {
  const result = [];
  asArray(value).forEach(function (raw) {
    const target = exactTargetAliases.get(normalizeLookup(raw));
    if (target && !result.includes(target)) result.push(target);
  });
  return result.includes(ALL_AGES) ? [ALL_AGES] : result;
}

function opportunityText(item) {
  return TEXT_FIELDS.flatMap(function (field) { return asArray(item && item[field]); })
    .map(normalizeText)
    .filter(Boolean)
    .join(" ");
}

export function inferTargets(text) {
  const normalized = normalizeText(text);
  if (/누구나|전\s*연령|연령\s*(?:무관|제한\s*없음)|나이\s*무관/.test(normalized)) {
    return [ALL_AGES];
  }

  const targets = [];
  if (/고등학생|고교생|고등학교\s*(?:학생|재학생)/.test(normalized)) {
    targets.push(HIGH_SCHOOL);
  }
  if (/대학생|학부생|전문대생|대학(?:교)?\s*재학생/.test(normalized)) {
    targets.push(COLLEGE);
  }
  return targets.length ? targets : [ALL_AGES];
}

export function resolveOpportunityTargets(item) {
  const explicit = normalizeExplicitTargets((item && (item.targets || item.target)) || []);
  if (explicit.length) return { targets: explicit, source: "explicit" };
  const inferred = inferTargets(opportunityText(item || {}));
  return {
    targets: inferred,
    source: inferred.includes(ALL_AGES) ? "fallback" : "inferred",
  };
}

export function matchesSelectedTargets(opportunityTargets, selectedTargets) {
  const selected = normalizeExplicitTargets(selectedTargets).filter(function (target) {
    return target !== ALL_AGES;
  });
  if (!selected.length) return true;
  const available = normalizeExplicitTargets(opportunityTargets);
  if (!available.length || available.includes(ALL_AGES)) return true;
  return selected.some(function (target) { return available.includes(target); });
}

export { ALL_AGES, HIGH_SCHOOL, COLLEGE };
