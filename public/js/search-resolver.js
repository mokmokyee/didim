/* DiDim standard keyword resolver. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.DiDimSearchResolver = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function normalizeText(value) {
    return String(value || "").normalize("NFKC").replace(/\s+/g, " ").trim();
  }

  function normalizeLookup(value) {
    return normalizeText(value)
      .toLocaleLowerCase("ko-KR")
      .replace(/[\s·._\-/]+/g, "");
  }

  function create(taxonomy) {
    const labels = taxonomy.keywords.map(function (item) { return String(item.label); });
    const labelSet = new Set(labels);
    const exactTerms = new Map();
    const categoryTerms = new Map();

    taxonomy.keywords.forEach(function (item) {
      [item.label].concat(item.aliases || []).forEach(function (term) {
        const normalized = normalizeLookup(term);
        if (!normalized) return;
        const matches = exactTerms.get(normalized) || [];
        if (!matches.includes(item.label)) matches.push(item.label);
        exactTerms.set(normalized, matches);
      });
    });

    Object.keys(taxonomy.filters || {}).forEach(function (category) {
      categoryTerms.set(normalizeLookup(category), category);
      taxonomy.filters[category].forEach(function (keyword) {
        if (!labelSet.has(keyword)) throw new Error("Unknown filter keyword: " + category + "/" + keyword);
      });
    });

    function categoriesFor(keywords) {
      const selected = new Set(keywords);
      return Object.keys(taxonomy.filters || {}).filter(function (category) {
        return taxonomy.filters[category].some(function (keyword) { return selected.has(keyword); });
      });
    }

    function directMatch(query) {
      const normalized = normalizeLookup(query);
      const category = categoryTerms.get(normalized);
      if (category) {
        return {
          mode: "category",
          source: "standard",
          keywords: taxonomy.filters[category].slice(),
          categories: [category],
        };
      }

      const keywords = exactTerms.get(normalized) || [];
      if (!keywords.length) return null;
      return {
        mode: "category",
        source: "standard",
        keywords: keywords.slice(),
        categories: categoriesFor(keywords),
      };
    }

    function validateKeywords(values) {
      const result = [];
      (Array.isArray(values) ? values : []).forEach(function (value) {
        const keyword = normalizeText(value);
        if (result.length < 12 && labelSet.has(keyword) && !result.includes(keyword)) result.push(keyword);
      });
      return result;
    }

    return {
      labels: labels.slice(),
      directMatch: directMatch,
      validateKeywords: validateKeywords,
    };
  }

  return { create: create, normalizeLookup: normalizeLookup, normalizeText: normalizeText };
});
