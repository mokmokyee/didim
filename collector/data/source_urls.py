from __future__ import annotations


WEVITY_URLS = [f"https://www.wevity.com/?c=find&s=1&gp={page}" for page in range(1, 11)]

LINKAREER_URLS = [
    "https://linkareer.com/list/contest?"
    "filterType=CATEGORY&orderBy_direction=DESC&orderBy_field=CREATED_AT"
    f"&page={page}"
    for page in range(1, 11)
]

CONTEST_KOREA_URLS = [
    "https://www.contestkorea.com/index.php?"
    "displayrow=12&int_gbn=1&Txt_key=all&Txt_word=&Txt_sortkey=a.int_sort"
    f"&Txt_sortword=desc&page={page}"
    for page in range(1, 11)
]

SOTONG_URLS = [
    "https://sotong.go.kr/front/epilogue/epilogueNewListPage.do?"
    "date_range=all&pagetype=bbs&search_title_contents=&preDate="
    "&epilogue_endde_cnddt=&endDate=&orderBy=&search_result="
    "&date_range_cnddt=all&search_result_cnddt=&epilogue_endde="
    "&search_insttNm=&epilogue_bgnde=&epilogue_bgnde_cnddt="
    f"&miv_pageNo={page}"
    for page in range(1, 6)
]

DREAMSPON_URLS = [
    f"https://www.dreamspon.com/scholarship/list.html?page={page}&ordby=1"
    for page in range(1, 3)
]

SEOUL_FUTURE_URLS = [
    "https://www.seoulfuture.or.kr/home/kor/M125164715/scholarship/info/index.do?",
    "https://www.seoulfuture.or.kr/home/kor/M338346211/scholarship/info/index.do?",
]

KOSAF_URLS = [
    "https://www.kosaf.go.kr/ko/scholar.do?pg=scholarship_main&naviParam=JH,00,00,00",
]

SOURCE_URLS = {
    "contest": WEVITY_URLS + LINKAREER_URLS + CONTEST_KOREA_URLS + SOTONG_URLS,
    "scholarship": DREAMSPON_URLS + SEOUL_FUTURE_URLS + KOSAF_URLS,
}
