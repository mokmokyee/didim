"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const taxonomy = require("../public/data/search_taxonomy.json");
const { create, normalizeLookup } = require("../public/js/search-resolver.js");

const resolver = create(taxonomy);

test("띄어쓰기를 제거한 표준 별칭은 상위 필터로 확장한다", () => {
  const result = resolver.directMatch("컴퓨터 과학");
  assert.equal(result.source, "standard");
  assert.deepEqual(result.keywords, ["소프트웨어"]);
  assert.deepEqual(result.categories, ["IT·기술"]);
});

test("필터 이름도 표준 검색어로 취급한다", () => {
  const result = resolver.directMatch("IT 기술");
  assert.deepEqual(result.categories, ["IT·기술"]);
  assert.ok(result.keywords.includes("인공지능"));
});

test("데이터 사이언스도 데이터 표준 키워드와 IT 분야로 매핑한다", () => {
  const result = resolver.directMatch("데이터 사이언스");
  assert.deepEqual(result.keywords, ["데이터"]);
  assert.deepEqual(result.categories, ["IT·기술"]);
});

test("Gemini 출력에서는 허용된 표준 키워드만 남긴다", () => {
  assert.deepEqual(
    resolver.validateKeywords(["소프트웨어", "없는키워드", "데이터", "데이터"]),
    ["소프트웨어", "데이터"],
  );
});

test("검색 비교용 정규화는 띄어쓰기와 구분 기호를 제거한다", () => {
  assert.equal(normalizeLookup(" 데이터-사이언스 "), "데이터사이언스");
});
