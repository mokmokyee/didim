/* DiDim opportunity region normalization and fallback inference. */
const REGION_TERMS = Object.freeze({
  "전국": ["전국", "전 지역", "지역 무관", "거주지 무관"],
  "서울": ["서울특별시", "서울"],
  "부산": ["부산광역시", "부산"],
  "대구": ["대구광역시", "대구"],
  "인천": ["인천광역시", "인천"],
  "광주": ["광주광역시", "광주"],
  "대전": ["대전광역시", "대전"],
  "울산": ["울산광역시", "울산"],
  "세종": ["세종특별자치시", "세종"],
  "경기": ["경기도"],
  "강원": ["강원특별자치도", "강원도", "강원"],
  "충북": ["충청북도", "충북"],
  "충남": ["충청남도", "충남"],
  "전북": ["전북특별자치도", "전라북도", "전북"],
  "전남": ["전라남도", "전남"],
  "경북": ["경상북도", "경북"],
  "경남": ["경상남도", "경남"],
  "제주": ["제주특별자치도", "제주도", "제주"],
});

const TEXT_FIELDS = Object.freeze([
  "title",
  "organization",
  "program_introduction",
  "summary",
  "description",
  "activity_content",
  "eligibility",
  "benefits",
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

const exactRegionAliases = new Map();
Object.entries(REGION_TERMS).forEach(function ([region, terms]) {
  [region].concat(terms).forEach(function (term) {
    exactRegionAliases.set(normalizeLookup(term), region);
  });
});

function normalizeExplicitRegions(value) {
  const result = [];
  asArray(value).forEach(function (raw) {
    const region = exactRegionAliases.get(normalizeLookup(raw));
    if (region && !result.includes(region)) result.push(region);
  });
  return result;
}

function opportunityText(item) {
  return TEXT_FIELDS.map(function (field) { return normalizeText(item && item[field]); })
    .filter(Boolean)
    .join(" ");
}

function resolveMode(item, text) {
  const explicit = normalizeLookup(item && (item.participation_mode || item.method));
  if (["online", "온라인"].includes(explicit)) return "online";
  if (["offline", "오프라인"].includes(explicit)) return "offline";
  if (["hybrid", "온오프라인병행", "온오프라인"].includes(explicit)) return "hybrid";

  const lookup = normalizeLookup(text);
  const hybrid = ["온오프라인", "온라인오프라인", "하이브리드", "병행운영"];
  const online = ["온라인", "비대면", "zoom", "줌"];
  const offline = ["오프라인", "현장진행", "현장참여", "대면진행", "대면참여"];
  if (hybrid.some(function (term) { return lookup.includes(normalizeLookup(term)); })) return "hybrid";
  const hasOnline = online.some(function (term) { return lookup.includes(normalizeLookup(term)); });
  const hasOffline = offline.some(function (term) { return lookup.includes(normalizeLookup(term)); });
  if (hasOnline && hasOffline) return "hybrid";
  if (hasOnline) return "online";
  if (hasOffline) return "offline";
  return "unknown";
}

function inferRegions(text) {
  const lookup = normalizeLookup(text);
  if (REGION_TERMS["전국"].some(function (term) { return lookup.includes(normalizeLookup(term)); })) {
    return ["전국"];
  }
  const result = [];
  Object.entries(REGION_TERMS).forEach(function ([region, terms]) {
    if (region === "전국") return;
    if (terms.some(function (term) { return lookup.includes(normalizeLookup(term)); })) result.push(region);
  });
  return result;
}

export function resolveOpportunityRegion(item) {
  const text = opportunityText(item || {});
  const mode = resolveMode(item || {}, text);
  const explicit = normalizeExplicitRegions((item && (item.regions || item.region)) || []);
  const inferred = explicit.length ? explicit : inferRegions(text);
  const regions = inferred.length ? inferred : (mode === "offline" ? [] : ["전국"]);
  return { mode, regions, source: explicit.length ? "explicit" : (inferred.length ? "inferred" : "fallback") };
}

export { normalizeExplicitRegions, normalizeLookup };
