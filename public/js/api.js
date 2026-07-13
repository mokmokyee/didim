/* DiDim Firebase adapter. No application server is required. */
(function () {
  "use strict";

  const SDK_VERSION = "12.16.0";
  const scriptUrl = document.currentScript && document.currentScript.src
    ? document.currentScript.src
    : new URL("js/api.js", document.baseURI).href;
  const scriptBase = new URL(".", scriptUrl);
  const fallbackDataUrl = new URL("../data/opportunities.json", scriptBase).href;
  const configModuleUrl = new URL("firebase-config.js", scriptBase).href;

  const TYPE_ALIASES = {
    contest: "공모전",
    scholarship: "장학금",
    공모전: "공모전",
    장학금: "장학금",
  };
  const MODE_ALIASES = {
    online: "온라인",
    offline: "오프라인",
    hybrid: "온·오프라인 병행",
    온라인: "온라인",
    오프라인: "오프라인",
    "온·오프라인 병행": "온·오프라인 병행",
  };
  const INTEREST_KEYWORDS = {
    교육: ["교육", "진로", "멘토링", "장학", "외국어"],
    "IT·기술": ["소프트웨어", "인공지능", "데이터", "정보보안", "로봇", "공학", "과학", "게임", "AI/IT"],
    디자인: ["그래픽디자인", "UX·UI", "산업디자인", "디자인"],
    예술: ["미술", "음악", "공연", "문학", "사진", "예술"],
    환경: ["환경", "기후", "에너지", "생태"],
    사회공헌: ["봉사", "복지", "인권", "지역사회", "공공정책", "사회공헌"],
    창업: ["창업", "스타트업", "경영", "창업/아이디어"],
    금융: ["금융", "경제", "회계", "투자"],
    마케팅: ["마케팅", "광고", "브랜딩", "홍보"],
    콘텐츠: ["콘텐츠제작", "영상", "방송", "미디어", "웹툰", "게임", "사진", "콘텐츠"],
  };

  let firebaseApp = null;
  let firebaseAuth = null;
  let firebaseDb = null;
  let firebaseProvider = null;
  let authSdk = null;
  let firestoreSdk = null;
  let authReady = Promise.resolve(null);
  let firebaseEnabled = false;
  let opportunityCache = null;

  function makeError(message, status, code) {
    const error = new Error(message);
    error.status = status;
    error.code = code;
    return error;
  }

  async function initialize() {
    try {
      const configModule = await import(configModuleUrl);
      const config = configModule.firebaseConfig;
      const appSdk = await import("https://www.gstatic.com/firebasejs/" + SDK_VERSION + "/firebase-app.js");
      authSdk = await import("https://www.gstatic.com/firebasejs/" + SDK_VERSION + "/firebase-auth.js");
      firestoreSdk = await import("https://www.gstatic.com/firebasejs/" + SDK_VERSION + "/firebase-firestore.js");
      firebaseApp = appSdk.getApps().length ? appSdk.getApp() : appSdk.initializeApp(config);
      firebaseAuth = authSdk.getAuth(firebaseApp);
      firebaseAuth.languageCode = "ko";
      firebaseProvider = new authSdk.GoogleAuthProvider();
      firebaseProvider.setCustomParameters({ prompt: "select_account" });
      firebaseDb = firestoreSdk.getFirestore(firebaseApp);
      firebaseEnabled = true;
      authReady = new Promise(function (resolve) {
        const unsubscribe = authSdk.onAuthStateChanged(firebaseAuth, function (user) {
          unsubscribe();
          resolve(user || null);
        });
      });
      return authReady;
    } catch (error) {
      console.error("Firebase 초기화에 실패했습니다.", error);
      firebaseEnabled = false;
      throw makeError("Firebase 연결을 초기화하지 못했어요.", 503, "firebase_init_failed");
    }
  }

  const ready = initialize();

  async function currentUser() {
    await ready;
    await authReady;
    return firebaseAuth ? firebaseAuth.currentUser : null;
  }

  async function requireUser() {
    const user = await currentUser();
    if (!user) throw makeError("로그인이 필요합니다.", 401, "auth_required");
    return user;
  }

  async function currentUid() {
    return (await requireUser()).uid;
  }

  function asArray(value) {
    if (Array.isArray(value)) return value.filter(Boolean).map(String);
    if (value === undefined || value === null || value === "") return [];
    return [String(value)];
  }

  function firstText(value) {
    return asArray(value).join(", ");
  }

  function normalizeText(value) {
    return String(value || "").normalize("NFKC").replace(/\s+/g, " ").trim();
  }

  function unique(values) {
    return Array.from(new Set((values || []).map(normalizeText).filter(Boolean)));
  }

  function dateOnly(value) {
    if (!value) return "";
    if (typeof value.toDate === "function") return value.toDate().toISOString().slice(0, 10);
    return String(value).slice(0, 10);
  }

  function daysUntil(value) {
    const raw = dateOnly(value);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) return null;
    const end = new Date(raw + "T00:00:00");
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    return Math.round((end.getTime() - today.getTime()) / 86400000);
  }

  function displayType(value) {
    return TYPE_ALIASES[value] || value || "프로그램";
  }

  function displayMode(value) {
    return MODE_ALIASES[value] || "";
  }

  function mapOpportunity(item) {
    if (!item || item.id === undefined || item.id === null) return null;
    const keywords = unique(asArray(item.keywords).concat(asArray(item.category)));
    const targets = unique(asArray(item.targets || item.target));
    const regions = unique(asArray(item.regions || item.region));
    const endDate = dateOnly(item.end_date || item.recruitmentEndDate);
    const calculatedDDay = daysUntil(endDate);
    const dDay = calculatedDDay === null
      ? (item.d_day === null || item.d_day === undefined ? null : Number(item.d_day))
      : calculatedDDay;
    const sourceActive = item.source_active !== false && item.sourceActive !== false;
    const status = !sourceActive || (dDay !== null && dDay < 0)
      ? "closed"
      : (dDay !== null && dDay <= 7 ? "urgent" : (item.status || "open"));
    const mode = item.participation_mode || item.method || "unknown";
    return {
      id: String(item.id),
      title: item.title || "",
      type: displayType(item.type),
      organization: item.organization || "",
      thumbnail: item.thumbnail || null,
      summary: item.program_introduction || item.summary || item.description || "",
      description: item.program_introduction || item.description || item.summary || "",
      target: firstText(targets),
      ageRequirement: item.age_requirement || item.ageRequirement || "",
      category: keywords,
      method: displayMode(mode),
      region: firstText(regions),
      recruitmentStartDate: dateOnly(item.start_date || item.recruitmentStartDate),
      recruitmentEndDate: endDate,
      applicationUrl: item.detail_url || item.applicationUrl || "",
      benefits: item.benefits || "",
      requirements: item.eligibility || item.requirements || "",
      documents: item.required_documents || item.documents || "",
      contact: item.contact || "",
      viewCount: Number(item.view_count || item.viewCount || 0),
      saveCount: Number(item.save_count || item.saveCount || 0),
      createdAt: dateOnly(item.first_seen_at || item.created_at || item.createdAt),
      status: status,
      dDay: dDay,
      activities: item.activity_content || item.activities || "",
      source: item.source || "",
      sourceActive: sourceActive,
      recommendationReason: item.recommendation_reason || item.recommendationReason || "",
      _keywords: keywords,
      _targets: targets,
      _regions: regions,
      _mode: mode,
      _rawType: item.type || "",
    };
  }

  async function fallbackOpportunities() {
    const response = await fetch(fallbackDataUrl, { cache: "no-cache" });
    if (!response.ok) return [];
    const payload = await response.json();
    return Array.isArray(payload) ? payload : (payload.items || []);
  }

  async function loadOpportunityDocuments(force) {
    await ready;
    if (opportunityCache && !force) return opportunityCache.slice();

    let items = [];
    const metaReference = firestoreSdk.doc(firebaseDb, "catalog", "opportunities");
    const metaSnapshot = await firestoreSdk.getDoc(metaReference);
    if (metaSnapshot.exists()) {
      const meta = metaSnapshot.data() || {};
      const chunkIds = asArray(meta.chunk_ids);
      const chunks = await Promise.all(chunkIds.map(function (chunkId) {
        return firestoreSdk.getDoc(firestoreSdk.doc(firebaseDb, "catalog_chunks", chunkId));
      }));
      chunks.forEach(function (snapshot) {
        if (snapshot.exists()) items.push.apply(items, asArrayObjects(snapshot.data().items));
      });
    }

    if (!items.length) {
      const snapshots = await firestoreSdk.getDocs(firestoreSdk.collection(firebaseDb, "opportunities"));
      snapshots.forEach(function (snapshot) {
        items.push(Object.assign({ id: snapshot.id }, snapshot.data()));
      });
    }
    if (!items.length) items = await fallbackOpportunities();
    opportunityCache = items.filter(function (item) { return item && item.source_active !== false; });
    return opportunityCache.slice();
  }

  function asArrayObjects(value) {
    return Array.isArray(value) ? value.filter(function (item) { return item && typeof item === "object"; }) : [];
  }

  function selected(values) {
    return new Set(asArray(values).map(normalizeText));
  }

  function matchesCategory(item, categories) {
    if (!categories.size) return true;
    const itemKeywords = new Set(item._keywords.map(normalizeText));
    for (const category of categories) {
      const mapped = INTEREST_KEYWORDS[category] || [category];
      if (mapped.some(function (keyword) {
        const normalized = normalizeText(keyword);
        return itemKeywords.has(normalized) || item._keywords.some(function (value) {
          return normalizeText(value).includes(normalized) || normalized.includes(normalizeText(value));
        });
      })) return true;
    }
    return false;
  }

  function matchesRegion(item, regions) {
    if (!regions.size) return true;
    if (item._mode === "online" || item._mode === "hybrid") return true;
    if (item._regions.includes("전국")) return true;
    return item._regions.some(function (region) { return regions.has(region); });
  }

  function matchesQuery(item, query) {
    const normalized = normalizeText(query).toLocaleLowerCase("ko-KR");
    if (!normalized) return true;
    const interestTerms = INTEREST_KEYWORDS[query] || [];
    const blob = [
      item.title,
      item.organization,
      item.summary,
      item.target,
      item.region,
      item.type,
      item.category.join(" "),
    ].join(" ").toLocaleLowerCase("ko-KR");
    return blob.includes(normalized) || interestTerms.some(function (term) {
      return blob.includes(normalizeText(term).toLocaleLowerCase("ko-KR"));
    });
  }

  function sortItems(items, sort) {
    if (sort === "views") {
      items.sort(function (a, b) { return b.viewCount - a.viewCount; });
    } else if (sort === "deadline") {
      items.sort(function (a, b) {
        return (a.dDay === null ? Number.MAX_SAFE_INTEGER : a.dDay) -
          (b.dDay === null ? Number.MAX_SAFE_INTEGER : b.dDay);
      });
    } else {
      items.sort(function (a, b) {
        return (b.viewCount + b.saveCount * 2) - (a.viewCount + a.saveCount * 2);
      });
    }
    return items;
  }

  async function findOpportunities(filters) {
    const values = filters || {};
    const types = selected(values.type || values.types);
    const targets = selected(values.target || values.targets);
    const categories = selected(values.category || values.categories);
    const regions = selected(values.region || values.regions);
    const query = values.query || values.q || "";
    const status = values.status || "active";
    const page = Math.max(1, Number(values.page || 1));
    const pageSize = Math.min(100, Math.max(1, Number(values.page_size || 24)));
    let items = (await loadOpportunityDocuments()).map(mapOpportunity).filter(Boolean);
    items = items.filter(function (item) {
      if (!item.sourceActive) return false;
      if (status !== "any" && status !== "closed" && item.status === "closed") return false;
      if (status === "closed" && item.status !== "closed") return false;
      if (types.size && !types.has(item.type)) return false;
      if (targets.size && !item._targets.some(function (target) { return targets.has(target); })) return false;
      if (!matchesCategory(item, categories)) return false;
      if (!matchesRegion(item, regions)) return false;
      return matchesQuery(item, query);
    });
    sortItems(items, values.sort || "recommend");
    const total = items.length;
    const start = (page - 1) * pageSize;
    return {
      items: items.slice(start, start + pageSize),
      total: total,
      page: page,
      pages: Math.ceil(total / pageSize),
      matchedKeywords: INTEREST_KEYWORDS[query] || [],
    };
  }

  async function listOpportunities(filters) {
    return findOpportunities(filters || {});
  }

  async function searchOpportunities(filters) {
    const values = filters || {};
    if (!normalizeText(values.query || values.q)) {
      throw makeError("검색어를 입력해 주세요.", 400, "query_required");
    }
    return findOpportunities(values);
  }

  async function recordView(opportunityId) {
    const user = await currentUser();
    if (!user) return;
    const reference = firestoreSdk.doc(firebaseDb, "opportunity_views", opportunityId + "_" + user.uid);
    try {
      await firestoreSdk.setDoc(reference, {
        opportunity_id: opportunityId,
        uid: user.uid,
        viewed_at: firestoreSdk.serverTimestamp(),
      });
    } catch (error) {
      if (error && error.code !== "permission-denied" && error.code !== "already-exists") {
        console.warn("조회 기록을 저장하지 못했습니다.");
      }
    }
  }

  async function getOpportunity(id) {
    await ready;
    const opportunityId = String(id);
    const snapshot = await firestoreSdk.getDoc(firestoreSdk.doc(firebaseDb, "opportunities", opportunityId));
    let item = snapshot.exists() ? Object.assign({ id: snapshot.id }, snapshot.data()) : null;
    if (!item) {
      item = (await loadOpportunityDocuments()).find(function (value) {
        return String(value.id) === opportunityId;
      }) || null;
    }
    if (!item) throw makeError("프로그램을 찾을 수 없어요.", 404, "not_found");
    recordView(opportunityId).catch(function () {});
    return mapOpportunity(item);
  }

  async function signInGoogle() {
    await ready;
    const result = await authSdk.signInWithPopup(firebaseAuth, firebaseProvider);
    return result.user;
  }

  async function signOut() {
    await ready;
    await authSdk.signOut(firebaseAuth);
  }

  function normalizedInterestKeywords(displayValues) {
    const result = [];
    asArray(displayValues).forEach(function (value) {
      const mapped = INTEREST_KEYWORDS[value] || [value];
      mapped.forEach(function (keyword) {
        if (keyword && !result.includes(keyword)) result.push(keyword);
      });
    });
    return result.slice(0, 40);
  }

  async function getUserProfile() {
    const user = await requireUser();
    const snapshot = await firestoreSdk.getDoc(firestoreSdk.doc(firebaseDb, "users", user.uid));
    if (!snapshot.exists()) throw makeError("사용자 정보를 찾을 수 없어요.", 404, "user_not_found");
    return Object.assign({ uid: user.uid }, snapshot.data());
  }

  async function putUserProfile(profile) {
    const user = await requireUser();
    const values = profile || {};
    const displayValues = unique(values.interest_display_values || values.interests || []);
    const reference = firestoreSdk.doc(firebaseDb, "users", user.uid);
    const existingSnapshot = await firestoreSdk.getDoc(reference);
    const existing = existingSnapshot.exists() ? existingSnapshot.data() : {};
    const now = new Date().toISOString();
    const payload = {
      uid: user.uid,
      name: normalizeText(values.name || existing.name || user.displayName || "").slice(0, 80),
      email: normalizeText(values.email || existing.email || user.email || "").slice(0, 254),
      birth_date: dateOnly(values.birth_date || values.birthDate || existing.birth_date),
      user_type: normalizeText(values.user_type || values.userType || existing.user_type || "").slice(0, 20),
      interest_display_values: displayValues.slice(0, 20),
      interest_keywords: normalizedInterestKeywords(displayValues),
      preferred_regions: unique(values.preferred_regions || values.preferredRegions || existing.preferred_regions || []).slice(0, 18),
      notification_settings: values.notification_settings || values.notificationSettings || existing.notification_settings || {},
      created_at: existing.created_at || now,
      updated_at: now,
    };
    await firestoreSdk.setDoc(reference, payload, { merge: true });
    return payload;
  }

  async function deleteUserProfile() {
    const user = await requireUser();
    const savedCollection = firestoreSdk.collection(firebaseDb, "users", user.uid, "saved_opportunities");
    const savedSnapshots = await firestoreSdk.getDocs(savedCollection);
    const batch = firestoreSdk.writeBatch(firebaseDb);
    savedSnapshots.forEach(function (snapshot) { batch.delete(snapshot.ref); });
    batch.delete(firestoreSdk.doc(firebaseDb, "users", user.uid));
    await batch.commit();
    await authSdk.deleteUser(user);
    return { deleted: true };
  }

  async function savedDocuments() {
    const user = await requireUser();
    const snapshots = await firestoreSdk.getDocs(
      firestoreSdk.collection(firebaseDb, "users", user.uid, "saved_opportunities")
    );
    const values = [];
    snapshots.forEach(function (snapshot) {
      values.push(Object.assign({ opportunity_id: snapshot.id }, snapshot.data()));
    });
    values.sort(function (a, b) { return String(b.saved_at || "").localeCompare(String(a.saved_at || "")); });
    return values;
  }

  async function saved(status, sort) {
    const savedValues = await savedDocuments();
    const order = new Map(savedValues.map(function (item, index) {
      return [String(item.opportunity_id), index];
    }));
    let items = (await loadOpportunityDocuments()).map(mapOpportunity).filter(function (item) {
      if (!item || !order.has(String(item.id))) return false;
      if (status === "open" || status === "recruiting") return item.status !== "closed";
      if (status === "closed") return item.status === "closed";
      return true;
    });
    if (sort && sort.indexOf("deadline") === 0) {
      items.sort(function (a, b) {
        const first = a.dDay === null ? Number.MAX_SAFE_INTEGER : a.dDay;
        const second = b.dDay === null ? Number.MAX_SAFE_INTEGER : b.dDay;
        return sort === "deadline-desc" ? second - first : first - second;
      });
    } else {
      items.sort(function (a, b) { return order.get(String(a.id)) - order.get(String(b.id)); });
    }
    return { items: items, total: items.length, page: 1, pages: items.length ? 1 : 0 };
  }

  async function setSaved(id, value) {
    const user = await requireUser();
    const opportunityId = String(id);
    const reference = firestoreSdk.doc(
      firebaseDb,
      "users",
      user.uid,
      "saved_opportunities",
      opportunityId
    );
    if (value) {
      await firestoreSdk.setDoc(reference, {
        opportunity_id: opportunityId,
        saved_at: new Date().toISOString(),
      });
    } else {
      await firestoreSdk.deleteDoc(reference);
    }
    return { saved: Boolean(value) };
  }

  async function recommendations(limit) {
    const profile = await getUserProfile();
    const savedValues = await savedDocuments();
    const savedIds = new Set(savedValues.map(function (item) { return String(item.opportunity_id); }));
    const candidates = (await loadOpportunityDocuments()).map(mapOpportunity).filter(function (item) {
      return item && item.sourceActive && item.status !== "closed";
    });
    const interests = new Set(asArray(profile.interest_keywords));
    const preferredRegions = new Set(asArray(profile.preferred_regions));
    const userType = String(profile.user_type || "");
    const savedKeywords = new Set();
    candidates.forEach(function (item) {
      if (savedIds.has(String(item.id))) item._keywords.forEach(function (keyword) { savedKeywords.add(keyword); });
    });
    const scored = candidates.map(function (item) {
      let score = 0;
      const reasons = [];
      const overlap = item._keywords.filter(function (keyword) { return interests.has(keyword); });
      if (overlap.length) {
        score += overlap.length * 20;
        reasons.push("관심 분야 " + overlap.join(", "));
      }
      const savedOverlap = item._keywords.filter(function (keyword) { return savedKeywords.has(keyword); });
      if (savedOverlap.length) {
        score += savedOverlap.length * 6;
        reasons.push("저장한 프로그램과 비슷한 분야");
      }
      if (userType && item._targets.includes(userType)) {
        score += 15;
        reasons.push("모집 대상");
      }
      if (preferredRegions.size && (item._mode === "online" || item._mode === "hybrid" ||
        item._regions.some(function (region) { return preferredRegions.has(region); }))) {
        score += 10;
        reasons.push("선호 지역");
      }
      score += Math.min(Math.floor(item.viewCount / 500), 5);
      return {
        item: Object.assign({}, item, {
          recommendationReason: reasons.length
            ? reasons.join(" · ") + " 조건과 잘 맞는 프로그램이에요."
            : "현재 모집 중인 프로그램 중 인기도가 높은 프로그램이에요.",
        }),
        score: score,
      };
    });
    scored.sort(function (a, b) {
      return b.score - a.score ||
        (a.item.dDay === null ? 999999 : a.item.dDay) - (b.item.dDay === null ? 999999 : b.item.dDay);
    });
    return scored.slice(0, Math.min(50, Math.max(1, Number(limit || 20)))).map(function (value) {
      return value.item;
    });
  }

  window.DiDimAPI = {
    ready: ready,
    hasFirebase: function () { return firebaseEnabled; },
    currentUser: currentUser,
    currentUid: currentUid,
    listOpportunities: listOpportunities,
    searchOpportunities: searchOpportunities,
    getOpportunity: getOpportunity,
    signInGoogle: signInGoogle,
    signOut: signOut,
    getUserProfile: getUserProfile,
    putUserProfile: putUserProfile,
    deleteUserProfile: deleteUserProfile,
    recommendations: recommendations,
    saved: saved,
    setSaved: setSaved,
    mapOpportunity: mapOpportunity,
  };
})();
