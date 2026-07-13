import test from "node:test";
import assert from "node:assert/strict";
import {
  matchesSelectedTargets,
  resolveOpportunityTargets,
} from "../public/js/target-resolver.mjs";

test("대상 근거가 없으면 전 연령으로 보완한다", () => {
  const result = resolveOpportunityTargets({ title: "데이터 분석 공모전" });
  assert.deepEqual(result.targets, ["전 연령"]);
  assert.equal(result.source, "fallback");
});

test("고등학생이 명시된 공고만 고등학생으로 분류한다", () => {
  const result = resolveOpportunityTargets({ eligibility: "전국 고등학생 지원 가능" });
  assert.deepEqual(result.targets, ["고등학생"]);
  assert.equal(result.source, "inferred");
});

test("대학생이 명시된 공고만 대학생으로 분류한다", () => {
  const result = resolveOpportunityTargets({ title: "대학생 서포터즈 모집" });
  assert.deepEqual(result.targets, ["대학생"]);
});

test("청소년이나 대학원생만 적힌 공고는 대상이 확정되지 않은 것으로 본다", () => {
  assert.deepEqual(resolveOpportunityTargets({ eligibility: "청소년 참가 가능" }).targets, ["전 연령"]);
  assert.deepEqual(resolveOpportunityTargets({ eligibility: "대학원생 연구자 대상" }).targets, ["전 연령"]);
});

test("누구나 참여할 수 있으면 전 연령을 우선한다", () => {
  const result = resolveOpportunityTargets({ description: "대상: 누구나, 고등학생, 대학생" });
  assert.deepEqual(result.targets, ["전 연령"]);
});

test("학생 필터는 해당 대상과 전 연령 공고를 함께 포함한다", () => {
  assert.equal(matchesSelectedTargets(["고등학생"], ["고등학생"]), true);
  assert.equal(matchesSelectedTargets(["대학생"], ["고등학생"]), false);
  assert.equal(matchesSelectedTargets(["전 연령"], ["고등학생"]), true);
  assert.equal(matchesSelectedTargets([], ["대학생"]), true);
});
