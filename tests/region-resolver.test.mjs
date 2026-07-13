import test from "node:test";
import assert from "node:assert/strict";
import { resolveOpportunityRegion } from "../public/js/region-resolver.mjs";

test("정식 행정구역 표기를 화면 필터 값으로 정규화한다", () => {
  const result = resolveOpportunityRegion({ participation_mode: "offline", regions: ["서울특별시"] });
  assert.equal(result.mode, "offline");
  assert.deepEqual(result.regions, ["서울"]);
  assert.equal(result.source, "explicit");
});

test("지역 배열이 없으면 공고 제목과 기관명에서 지역을 추론한다", () => {
  const result = resolveOpportunityRegion({ title: "부산 청년 아이디어 공모전", organization: "부산광역시" });
  assert.deepEqual(result.regions, ["부산"]);
  assert.equal(result.source, "inferred");
});

test("지역 정보가 없는 참여형 공고는 전국 공고로 보완한다", () => {
  const result = resolveOpportunityRegion({ title: "데이터 분석 아이디어 공모전" });
  assert.equal(result.mode, "unknown");
  assert.deepEqual(result.regions, ["전국"]);
  assert.equal(result.source, "fallback");
});

test("장소를 알 수 없는 오프라인 공고는 전국으로 단정하지 않는다", () => {
  const result = resolveOpportunityRegion({ title: "현장 참여 행사", participation_mode: "offline" });
  assert.deepEqual(result.regions, []);
});

test("진행 방식이 비어 있어도 설명에서 온라인 여부를 추론한다", () => {
  const result = resolveOpportunityRegion({ program_introduction: "모든 일정은 비대면 Zoom으로 진행됩니다." });
  assert.equal(result.mode, "online");
  assert.deepEqual(result.regions, ["전국"]);
});
