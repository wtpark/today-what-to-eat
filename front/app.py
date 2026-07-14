from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components

API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
APP_BUILD = os.getenv("APP_BUILD", "final-fixed2")
KST = ZoneInfo("Asia/Seoul")
TIMEOUT = 15

st.set_page_config(page_title="오늘 뭐먹지", page_icon="🍽️", layout="wide", initial_sidebar_state="collapsed")

st.markdown(
    """
    <style>
      .stApp { background: linear-gradient(180deg, #fbfcfa 0%, #f3f6f2 100%); color: #1d2922; }
      .block-container { max-width: 1200px; padding-top: 1.2rem; padding-bottom: 3rem; }
      .hero {
        border: 1px solid #dfe7df; border-radius: 24px; padding: 1.35rem 1.5rem;
        background: #ffffff; box-shadow: 0 10px 30px rgba(40,70,50,.07); margin-bottom: 1rem;
      }
      .hero h1 { margin: 0; font-size: 2rem; color: #1d2922; }
      .hero p { margin: .45rem 0 0; color: #52615a; }
      .summary-box {
        border: 1px solid #dfe7df; border-radius: 16px; padding: .9rem 1rem;
        background: #ffffff; color: #1d2922; margin-bottom: .7rem;
      }
      .analysis-box {
        border-left: 5px solid #718a75; border-radius: 12px; padding: .85rem 1rem;
        background: #f5f8f4; color: #1d2922; margin: .4rem 0;
      }
      div[data-testid="stMetric"] { background: #ffffff; border: 1px solid #e1e8e2; padding: .8rem; border-radius: 16px; }
      div[data-testid="stForm"] { border: 1px solid #e1e8e2; border-radius: 18px; padding: 1rem; background: #ffffff; }
      .small-muted { color: #65736a; font-size: .9rem; }
      .fridge-shell {
        max-width: 920px; margin: .5rem auto 1.2rem; padding: 1.15rem;
        border: 3px solid #aab4b0; border-radius: 30px;
        background: linear-gradient(145deg, #f8faf9 0%, #dfe5e2 48%, #f5f7f6 100%);
        box-shadow: 0 22px 50px rgba(45, 60, 52, .18), inset 0 1px 0 #fff;
      }
      .fridge-display {
        width: fit-content; margin: 0 auto 1rem; padding: .55rem 1.1rem;
        border-radius: 12px; background: #24352d; color: #eaf8ef;
        font-weight: 700; letter-spacing: .02em; box-shadow: inset 0 0 0 1px #4e6559;
      }
      .fridge-grid { display: grid; grid-template-columns: 1fr 1fr; gap: .65rem; }
      .fridge-door {
        position: relative; min-height: 150px; padding: 1.25rem 1.5rem;
        border: 1px solid #aeb8b3; border-radius: 18px;
        background: linear-gradient(135deg, #ffffff 0%, #e9eeeb 55%, #d4dcda 100%);
        color: #1d2922 !important; text-decoration: none !important;
        box-shadow: inset 0 1px 0 #fff, 0 8px 18px rgba(50, 65, 58, .10);
        display: flex; flex-direction: column; justify-content: center;
        transition: transform .12s ease, box-shadow .12s ease;
      }
      .fridge-door:hover { transform: translateY(-2px); box-shadow: inset 0 1px 0 #fff, 0 12px 24px rgba(50,65,58,.16); }
      .fridge-door::after {
        content: ""; position: absolute; top: 24px; bottom: 24px; width: 7px;
        border-radius: 6px; background: linear-gradient(180deg, #7d8984, #bec6c2);
      }
      .fridge-door:nth-child(odd)::after { right: 13px; }
      .fridge-door:nth-child(even)::after { left: 13px; }
      .fridge-icon { font-size: 2rem; margin-bottom: .35rem; }
      .fridge-title { font-size: 1.25rem; font-weight: 800; }
      .fridge-desc { color: #58665e; font-size: .92rem; margin-top: .25rem; }
      .fridge-foot { text-align: center; color: #607067; margin-top: .8rem; font-size: .88rem; }
      .status-chip {
        display: inline-block; border-radius: 999px; padding: .25rem .65rem;
        background: #e7f2e9; color: #285b36; font-weight: 700; margin-right: .3rem;
      }
      .completion-box {
        border: 2px solid #78907d; border-radius: 20px; padding: 1rem 1.2rem;
        background: #f4faf5; color: #1d2922; margin: 1rem 0;
        box-shadow: 0 8px 22px rgba(50, 80, 60, .08);
      }
      @media (max-width: 720px) {
        .fridge-grid { grid-template-columns: 1fr; }
        .fridge-door::after { right: 13px !important; left: auto !important; }
      }
    </style>
    """,
    unsafe_allow_html=True,
)


class ApiError(RuntimeError):
    pass


def api_request(method: str, path: str, **kwargs):
    try:
        response = requests.request(method, f"{API_URL}{path}", timeout=TIMEOUT, **kwargs)
    except requests.RequestException as exc:
        raise ApiError(f"FastAPI에 연결할 수 없습니다: {exc}") from exc
    if response.status_code == 204:
        return None
    try:
        body = response.json()
    except ValueError:
        body = {"detail": response.text or "알 수 없는 응답"}
    if not response.ok:
        raise ApiError(str(body.get("detail", body)))
    return body


def show_api_error(exc: Exception):
    st.error(str(exc))
    st.caption(f"API 주소: {API_URL}")


def nav_to(label: str):
    st.session_state["_next_nav"] = label
    st.rerun()


def invalidate_recommendation() -> None:
    """Discard output calculated from an older pantry or inventory state."""
    st.session_state.recommendation_result = None
    st.session_state.selected_recipe = None
    st.session_state.scroll_to_completion = False
    st.session_state.completion_result = None
    st.session_state.scroll_to_completion_result = False


def get_health() -> dict[str, Any] | None:
    try:
        return api_request("GET", "/health")
    except ApiError:
        return None


def meal_slot_now() -> str:
    hour = datetime.now(KST).hour
    if hour < 10:
        return "아침"
    if hour < 15:
        return "점심"
    if hour < 21:
        return "저녁"
    return "야식"


def cuisine_emoji(cuisine: str) -> str:
    return {"한식": "🍚", "중식": "🥢", "일식": "🍱", "양식": "🍝"}.get(cuisine, "🍽️")


def format_tools(tools: list[Any]) -> str:
    if not tools:
        return "필요 없음"
    labels: list[str] = []
    for requirement in tools:
        if isinstance(requirement, list):
            labels.append(" 또는 ".join(requirement))
        else:
            labels.append(str(requirement))
    return " · ".join(labels)


def missing_label(item: dict[str, Any]) -> str:
    prefix = {"ingredient": "재료", "core_option": "선택 재료", "seasoning": "핵심 양념"}.get(item.get("type"), "항목")
    return f"{prefix}: {item['name']}"


def format_ingredient_option(item: dict[str, Any]) -> str:
    """Avoid redundant labels such as '두부 · 두부'."""
    name = str(item["name"]).strip()
    category = str(CATEGORY_LABELS.get(item["category"], item["category"])).strip()
    return name if name == category else f"{name} · {category}"


def render_recipe_card(recipe: dict[str, Any], rank: int, section_key: str, allow_complete: bool = True):
    with st.container(border=True):
        h1, h2, h3 = st.columns([3.2, 1, 1])
        h1.markdown(f"### {rank}. {cuisine_emoji(recipe['cuisine'])} {recipe['name']}")
        h2.metric("추천 적합도", f"{round(recipe['score'])}점")
        h3.metric("조리시간", f"{recipe['cook_time']}분")
        st.write(f"{recipe['cuisine']} · {recipe['meal_type']} · {recipe['cooking_method']} · 도구: {format_tools(recipe['tools'])}")

        for reason in recipe.get("reasons", [])[:3]:
            st.write(f"- {reason}")

        if recipe.get("substitutions_used"):
            st.info("대체 적용: " + " / ".join(recipe["substitutions_used"]))
        for warning in recipe.get("substitution_warnings", []):
            st.warning(warning)
        extras = recipe.get("optional_missing_ingredients", []) + recipe.get("optional_missing_seasonings", [])
        if extras:
            st.caption("있으면 더 좋아요: " + ", ".join(extras))

        with st.expander("점수와 추천 근거 자세히"):
            labels = {
                "priority": "우선 재료 활용",
                "completeness": "재료·양념 충족",
                "taste": "현재 취향",
                "diversity": "최근 식사 다양성",
                "convenience": "조리 편의성",
            }
            cols = st.columns(5)
            for idx, key in enumerate(["priority", "completeness", "taste", "diversity", "convenience"]):
                cols[idx].metric(labels[key], f"{recipe['score_breakdown'].get(key, 0):.1f} / {recipe['score_weights'][key]}")
            detail = recipe.get("score_details", {})
            st.caption(
                f"냉장고 재료 충족 {detail.get('ingredient_coverage', 0)}% · "
                f"양념 충족 {detail.get('pantry_coverage', 0)}% · "
                f"대체 사용 {detail.get('substitution_count', 0)}건"
            )
            if len(recipe.get("reasons", [])) > 3:
                st.write("전체 추천 근거")
                for reason in recipe.get("reasons", [])[3:]:
                    st.write(f"- {reason}")
            st.caption("추천 적합도는 식품 안전 확률이 아니라 후보 간 상대 순위를 위한 서비스 정책 점수입니다.")

        if allow_complete and st.button("이 메뉴로 먹었어요", key=f"eat_{section_key}_{recipe['recipe_id']}", type="primary"):
            st.session_state.selected_recipe = recipe
            st.session_state.scroll_to_completion = True
            st.rerun()


def render_one_more(recipe: dict[str, Any], rank: int, section_key: str):
    missing = " · ".join(missing_label(x) for x in recipe.get("missing_to_make", []))
    title = f"{rank}. {cuisine_emoji(recipe['cuisine'])} {recipe['name']} · {missing}"
    with st.expander(title):
        st.write(f"추천 적합도 {round(recipe['score'])}점 · {recipe['cook_time']}분 · {format_tools(recipe['tools'])}")
        st.write("아래 항목 하나를 채우면 바로 조리 후보가 됩니다.")
        for item in recipe.get("missing_to_make", []):
            st.write(f"- {missing_label(item)}")
        if recipe.get("substitutions_used"):
            st.info("현재 적용 가능한 대체: " + " / ".join(recipe["substitutions_used"]))
        for warning in recipe.get("substitution_warnings", []):
            st.warning(warning)
        for reason in recipe.get("reasons", [])[:3]:
            st.write(f"- {reason}")


def render_diagnostics(result: dict[str, Any]):
    diagnostics = result.get("diagnostics", {})
    messages = result.get("analysis_messages", [])
    if messages:
        st.markdown("### 조건 분석")
        for message in messages:
            st.markdown(f'<div class="analysis-box">{message}</div>', unsafe_allow_html=True)

    unlocks = diagnostics.get("unlock_suggestions", [])
    if unlocks:
        st.markdown("#### 추가하면 가능한 메뉴")
        for item in unlocks:
            recipe_text = ", ".join(item.get("recipe_names", []))
            st.write(f"- **{item['name']}** 추가 → {recipe_text}")

    with st.expander("후보가 줄어든 이유 보기"):
        counts = diagnostics.get("counts", {})
        if counts:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("조건 완전 일치", counts.get("preferred_exact_direct", 0))
            c2.metric("같은 계열·다른 형태", counts.get("preferred_other_type_direct", 0))
            c3.metric("다른 계열·형태 일치", counts.get("alternative_exact_direct", 0))
            c4.metric("다른 계열·다른 형태", counts.get("alternative_other_type_direct", 0))
        preferred_rejections = diagnostics.get("preferred_rejection_counts", {})
        if preferred_rejections:
            labels = {
                "time": "조리시간 초과",
                "tools": "필수 조리기구 부족",
                "previous_meal": "직전 식사 회피 조건",
                "strict_cuisine": "음식 계열 제한",
                "missing_many": "필수 재료·핵심 양념 2개 이상 부족",
            }
            st.write("선택한 음식 계열의 탈락 사유")
            for key, value in preferred_rejections.items():
                st.write(f"- {labels.get(key, key)}: {value}개")
        catalog = diagnostics.get("catalog_by_cuisine", {})
        if catalog:
            st.caption("음식 계열별 레시피: " + " · ".join(f"{k} {v}개" for k, v in catalog.items()))
        meal_catalog = diagnostics.get("catalog_by_meal_type", {})
        if meal_catalog:
            st.caption("식사 형태별 레시피: " + " · ".join(f"{k} {v}개" for k, v in meal_catalog.items()))


PANTRY_GROUPS = {
    "기본": ["salt", "sugar", "pepper", "cooking_oil", "soy_sauce", "vinegar", "minced_garlic", "ketchup"],
    "한식": ["sesame_oil", "soup_soy", "gochujang", "doenjang", "gochugaru", "pancake_mix", "sesame_seed"],
    "중식": ["oyster_sauce", "chunjang", "doubanjiang", "starch", "chili_oil"],
    "일식": ["mirin", "bonito_stock", "curry_powder", "mayonnaise"],
    "양식": ["butter", "olive_oil", "mustard", "honey", "chicken_stock", "worcestershire", "basil", "oregano"],
}

CATEGORY_LABELS = {
    "cooked_food": "조리식품",
    "fermented": "발효식품",
    "egg": "달걀",
    "tofu": "두부",
    "raw_meat": "육류",
    "seafood": "수산물",
    "canned": "캔·가공",
    "dairy": "유제품",
    "cheese": "치즈",
    "leafy_vegetable": "잎채소",
    "root_vegetable": "뿌리채소",
    "vegetable_leafy": "잎채소",
    "vegetable_root": "뿌리채소",
    "vegetable_general": "채소",
    "vegetable": "채소",
    "fruit_vegetable": "과채류",
    "bread": "빵·또띠아",
    "dry_food": "건식품",
    "dry_noodle": "건면",
    "noodle": "면",
    "processed_food": "가공식품",
    "processed_meat": "가공육",
    "frozen_food": "냉동식품",
}

COMMON_INGREDIENTS = ["egg", "onion", "pork", "chicken", "tofu", "soft_tofu", "dumpling", "milk", "bread", "pasta", "potato", "cabbage"]

for key, default in {
    "nav": "🏠 홈",
    "add_prefill": None,
    "form_generation": 0,
    "recommendation_result": None,
    "selected_recipe": None,
    "scroll_to_completion": False,
    "completion_result": None,
    "scroll_to_completion_result": False,
}.items():
    st.session_state.setdefault(key, default)

if "_next_nav" in st.session_state:
    st.session_state["nav"] = st.session_state.pop("_next_nav")

health = get_health()
st.markdown(
    """
    <div class="hero">
      <h1>🍽️ 오늘 뭐먹지</h1>
      <p>냉장고 선입선출 · 현재 취향 · 직전·최근 식사 · 저장된 양념장을 함께 반영합니다.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

nav_options = ["🏠 홈", "🧊 냉장고 현황", "➕ 식재료 추가", "🍳 메뉴 추천", "🧂 내 양념장"]
st.radio("메뉴", nav_options, horizontal=True, key="nav", label_visibility="collapsed")

with st.sidebar:
    st.subheader("서비스 상태")
    st.caption(f"빌드: {APP_BUILD}")
    if health:
        st.success("FastAPI · DB 연결됨")
        st.json(health, expanded=False)
        try:
            catalog = api_request("GET", "/catalog/summary")
            st.caption(f"식재료 {catalog['ingredients']}개 · 레시피 {catalog['recipes']}개 · 양념 {catalog['seasonings']}개")
        except ApiError:
            pass
    else:
        st.error("백엔드 연결 실패")
        st.code(API_URL)


if st.session_state.nav == "🏠 홈":
    try:
        home_inventory = api_request("GET", "/ingredients")
        home_seasonings = api_request("GET", "/seasonings")
        home_catalog = api_request("GET", "/catalog/summary")
    except ApiError as exc:
        show_api_error(exc)
        st.stop()

    hs = home_inventory["summary"]
    owned_count = sum(1 for item in home_seasonings if item["owned"])
    priority_names = [
        item["ingredient_name"] for item in home_inventory["items"]
        if item.get("priority_override") and item.get("recommendation_eligible")
    ]
    automatic_names = [
        item["ingredient_name"] for item in home_inventory["items"]
        if not item.get("priority_override") and item["action"] == "먼저 사용"
    ]
    urgent_names: list[str] = []
    for name in priority_names + automatic_names:
        if name not in urgent_names:
            urgent_names.append(name)
    urgent_text = ", ".join(urgent_names[:3]) if urgent_names else "급한 재료 없음"

    st.markdown(
        f'<div class="fridge-display">오늘 먼저 확인: {urgent_text}</div>',
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        row1_left, row1_right = st.columns(2)
        with row1_left:
            with st.container(border=True):
                st.markdown(
                    f'<div class="fridge-icon">🧊</div><div class="fridge-title">냉장고 현황</div>'
                    f'<div class="fridge-desc">재고 {hs["total"]}개 · 먼저 사용 {hs["use_first"]}개 · 보관 위치와 날짜 수정</div>',
                    unsafe_allow_html=True,
                )
                if st.button("냉장고 문 열기", key="home_inventory", use_container_width=True):
                    nav_to("🧊 냉장고 현황")
        with row1_right:
            with st.container(border=True):
                st.markdown(
                    '<div class="fridge-icon">➕</div><div class="fridge-title">식재료 추가</div>'
                    '<div class="fridge-desc">최근 재료 빠른 등록 · 구매 묶음별 선입선출 저장</div>',
                    unsafe_allow_html=True,
                )
                if st.button("식재료 문 열기", key="home_add", use_container_width=True):
                    nav_to("➕ 식재료 추가")
        row2_left, row2_right = st.columns(2)
        with row2_left:
            with st.container(border=True):
                st.markdown(
                    f'<div class="fridge-icon">🍳</div><div class="fridge-title">오늘 뭐먹지</div>'
                    f'<div class="fridge-desc">레시피 {home_catalog["recipes"]}개 · 5분 메뉴와 가벼운 식사 포함</div>',
                    unsafe_allow_html=True,
                )
                if st.button("추천 서랍 열기", key="home_recommend", use_container_width=True):
                    nav_to("🍳 메뉴 추천")
        with row2_right:
            with st.container(border=True):
                st.markdown(
                    f'<div class="fridge-icon">🧂</div><div class="fridge-title">내 양념장</div>'
                    f'<div class="fridge-desc">보유 양념 {owned_count}/{len(home_seasonings)}개 · 이전 체크 자동 저장</div>',
                    unsafe_allow_html=True,
                )
                if st.button("양념장 문 열기", key="home_pantry", use_container_width=True):
                    nav_to("🧂 내 양념장")
    st.caption("홈 메뉴는 Streamlit 버튼으로 이동하므로 추천 결과와 입력 상태가 브라우저 전체 새로고침으로 초기화되지 않습니다.")
    h1, h2, h3, h4 = st.columns(4)
    h1.metric("전체 재고", hs["total"])
    h2.metric("먼저 사용", hs["use_first"])
    h3.metric("추천 제외", hs.get("recommendation_excluded", hs.get("needs_review", 0)))
    h4.metric("레시피", home_catalog["recipes"])


elif st.session_state.nav == "🧊 냉장고 현황":
    st.subheader("내 냉장고")
    try:
        inventory_data = api_request("GET", "/ingredients")
    except ApiError as exc:
        show_api_error(exc)
        st.stop()

    summary = inventory_data["summary"]
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("전체 재고", summary["total"])
    c2.metric("먼저 사용", summary["use_first"])
    c3.metric("개봉 재료", summary["opened"])
    c4.metric("상태 확인", summary.get("status_review", 0))
    c5.metric("기한 경과", summary.get("expired", 0))
    c6.metric("사용자 제외", summary.get("user_excluded", 0))
    st.caption(f"표시기한 미입력 {summary['missing_expiry']}개 · 추천 제외 합계 {summary.get('recommendation_excluded', summary.get('needs_review', 0))}개")

    if not inventory_data["items"]:
        st.info("냉장고가 비어 있습니다. 직접 등록하거나 여러 음식 계열을 시험할 수 있는 균형 데모를 불러오세요.")
        a, b, c = st.columns(3)
        if a.button("➕ 직접 추가", use_container_width=True):
            nav_to("➕ 식재료 추가")
        if b.button("다국적 균형 데모", use_container_width=True):
            try:
                result = api_request("POST", "/demo/load", json={"only_when_empty": True, "profile": "balanced", "load_balanced_pantry": True})
                invalidate_recommendation()
                st.success(result["message"])
                st.rerun()
            except ApiError as exc:
                show_api_error(exc)
        if c.button("한식 중심 데모", use_container_width=True):
            try:
                result = api_request("POST", "/demo/load", json={"only_when_empty": True, "profile": "korean", "load_balanced_pantry": True})
                invalidate_recommendation()
                st.success(result["message"])
                st.rerun()
            except ApiError as exc:
                show_api_error(exc)
        st.stop()

    items = inventory_data["items"]
    f1, f2, f3 = st.columns([1, 1, 2])
    view_mode = f1.radio("보기", ["카드", "리스트"], horizontal=True)
    sort_mode = f2.selectbox("정렬", ["소비 우선도", "표시기한", "구매일", "이름"])
    search = f3.text_input("냉장고 검색", placeholder="식재료명 또는 상세명")

    filtered = [x for x in items if not search or search.lower() in f"{x['ingredient_name']} {x['detail_name']}".lower()]
    if sort_mode == "표시기한":
        filtered.sort(key=lambda x: (x["expiry_date"] is None, x["expiry_date"] or "9999-12-31"))
    elif sort_mode == "구매일":
        filtered.sort(key=lambda x: x["purchase_date"])
    elif sort_mode == "이름":
        filtered.sort(key=lambda x: x["ingredient_name"])
    else:
        filtered.sort(key=lambda x: -x["priority_score"])

    if view_mode == "리스트":
        frame = pd.DataFrame([
            {
                "ID": x["id"], "식재료": x["ingredient_name"], "상세": x["detail_name"],
                "수량": f"{x['quantity']:g} {x['unit']}", "보관": x["storage"], "구매일": x["purchase_date"],
                "표시기한": x["expiry_date"] or "미입력", "개봉": "예" if x["opened"] else "아니오",
                "소비 우선도": x["priority_score"], "상태": x["action"], "정보 신뢰도": x["confidence"],
            } for x in filtered
        ])
        st.dataframe(frame, use_container_width=True, hide_index=True)
    else:
        for item in filtered:
            with st.container(border=True):
                left, middle, right = st.columns([2.4, 1.1, 1.1])
                with left:
                    title = item["ingredient_name"] + (f" · {item['detail_name']}" if item["detail_name"] else "")
                    st.markdown(f"### {title}")
                    st.write(f"{item['quantity']:g} {item['unit']} · {item['storage']} · 구매 {item['purchase_date']}")
                    st.caption(
                        f"구매 묶음 #{item['id']} · 표시기한: {item['expiry_date'] or '미입력'} · "
                        f"개봉: {'예' if item['opened'] else '아니오'}"
                    )
                middle.metric("소비 우선도", f"{item['priority_score']:.1f}점")
                middle.caption(item["action"])
                right.metric("정보 신뢰도", item["confidence"])
                right.caption(item["confidence_reason"])

                with st.expander("점수 근거·재고 관리"):
                    cols = st.columns(4)
                    for idx, (name, value) in enumerate(item["priority_breakdown"].items()):
                        cols[idx].metric(name, f"{value:.1f}")
                    st.caption(f"{item.get('date_score_source', '입력 정보')}를 반영한 소비 순서 정책 점수입니다. 식품 안전 판정이 아닙니다.")
                    if item.get("condition_notes"):
                        st.warning("확인 항목: " + ", ".join(item["condition_notes"]))
                    keep_expiry = st.checkbox(
                        "표시기한 사용",
                        value=bool(item["expiry_date"]),
                        key=f"keep_expiry_edit_{item['id']}",
                    )
                    with st.form(f"edit_{item['id']}"):
                        st.markdown("#### 재고 정보 수정")
                        st.caption("식재료 종류 자체를 잘못 골랐다면 이 재고를 삭제한 뒤 다시 등록해주세요.")
                        er1, er2, er3 = st.columns(3)
                        new_detail = er1.text_input("상세명", value=item["detail_name"] or "")
                        new_qty = er2.number_input("현재 수량", min_value=0.0, value=float(item["quantity"]), step=0.5)
                        new_unit = er3.text_input("단위", value=item["unit"])

                        er4, er5, er6 = st.columns(3)
                        storage_options = ["냉장", "냉동", "실온"]
                        new_storage = er4.selectbox(
                            "보관 위치", storage_options, index=storage_options.index(item["storage"])
                        )
                        new_purchase_date = er5.date_input(
                            "구매일", value=date.fromisoformat(item["purchase_date"]), key=f"purchase_edit_{item['id']}"
                        )
                        new_expiry_date = None
                        if keep_expiry:
                            expiry_default = date.fromisoformat(item["expiry_date"]) if item["expiry_date"] else new_purchase_date
                            new_expiry_date = er6.date_input(
                                "표시기한", value=expiry_default, key=f"expiry_edit_{item['id']}"
                            )

                        er7, er8, er9 = st.columns(3)
                        new_opened = er7.checkbox("개봉함", value=bool(item["opened"]))
                        opened_default = date.fromisoformat(item["opened_date"]) if item.get("opened_date") else new_purchase_date
                        new_opened_date = er8.date_input(
                            "개봉일", value=opened_default, key=f"opened_edit_{item['id']}"
                        )
                        new_status = er9.selectbox(
                            "추천 상태", ["normal", "needs_review", "excluded"],
                            index=["normal", "needs_review", "excluded"].index(item["condition_status"]),
                            format_func=lambda x: {"normal": "정상", "needs_review": "직접 확인 필요", "excluded": "추천에서 제외"}[x],
                        )
                        priority_override = st.checkbox("사용자 지정 우선 사용", value=bool(item["priority_override"]))
                        note = st.text_input("메모", value=item["note"] or "")
                        if st.form_submit_button("수정 저장", type="primary", use_container_width=True):
                            try:
                                api_request(
                                    "PUT",
                                    f"/ingredients/{item['id']}",
                                    json={
                                        "detail_name": new_detail,
                                        "quantity": new_qty,
                                        "unit": new_unit,
                                        "storage": new_storage,
                                        "purchase_date": new_purchase_date.isoformat(),
                                        "expiry_date": new_expiry_date.isoformat() if new_expiry_date else None,
                                        "opened": new_opened,
                                        "opened_date": new_opened_date.isoformat() if new_opened else None,
                                        "condition_status": new_status,
                                        "priority_override": priority_override,
                                        "note": note,
                                    },
                                )
                                invalidate_recommendation()
                                st.success("보관 위치·구매일을 포함해 수정했습니다.")
                                st.rerun()
                            except ApiError as exc:
                                show_api_error(exc)
                    rc1, rc2 = st.columns(2)
                    if rc1.button("같은 제품 다시 샀어요", key=f"repurchase_{item['id']}", use_container_width=True):
                        st.session_state.add_prefill = item
                        st.session_state.form_generation += 1
                        nav_to("➕ 식재료 추가")
                    if rc2.button("이 재고 삭제", key=f"delete_{item['id']}", use_container_width=True, type="secondary"):
                        try:
                            api_request("DELETE", f"/ingredients/{item['id']}")
                            invalidate_recommendation()
                            st.success("삭제했습니다.")
                            st.rerun()
                        except ApiError as exc:
                            show_api_error(exc)


elif st.session_state.nav == "➕ 식재료 추가":
    st.subheader("식재료 등록")
    st.caption("자주 쓰는 재료를 빠르게 선택하고, 기본 정보만 입력해도 저장할 수 있습니다.")
    try:
        masters = api_request("GET", "/master/ingredients")
        inventory_data = api_request("GET", "/ingredients")
    except ApiError as exc:
        show_api_error(exc)
        st.stop()

    master_by_id = {x["id"]: x for x in masters}
    prefill = st.session_state.add_prefill or {}
    generation = st.session_state.form_generation

    recent_ids = []
    for item in sorted(inventory_data["items"], key=lambda x: x["id"], reverse=True):
        if item["ingredient_id"] not in recent_ids:
            recent_ids.append(item["ingredient_id"])
    recent_ids = recent_ids[:6]

    st.markdown("#### 빠른 선택")
    quick_ids = recent_ids or COMMON_INGREDIENTS[:6]
    quick_cols = st.columns(min(len(quick_ids), 6) or 1)
    for idx, ingredient_id in enumerate(quick_ids):
        if ingredient_id not in master_by_id:
            continue
        if quick_cols[idx % len(quick_cols)].button(master_by_id[ingredient_id]["name"], key=f"quick_recent_{ingredient_id}", use_container_width=True):
            st.session_state.add_prefill = {"ingredient_id": ingredient_id}
            st.session_state.form_generation += 1
            st.rerun()

    filter1, filter2 = st.columns(2)
    category_options = ["전체"] + sorted({CATEGORY_LABELS.get(x["category"], x["category"]) for x in masters})
    category_label = filter1.selectbox("카테고리", category_options)
    search = filter2.text_input("식재료 검색", placeholder="예: 치즈, 파스타, 닭고기")
    filtered_masters = []
    for item in masters:
        label = CATEGORY_LABELS.get(item["category"], item["category"])
        haystack = " ".join([item["name"], *item.get("aliases", []), label]).lower()
        if category_label != "전체" and label != category_label:
            continue
        if search and search.lower() not in haystack:
            continue
        filtered_masters.append(item)
    if not filtered_masters:
        st.warning("검색 조건에 맞는 식재료가 없습니다.")
        st.stop()

    selected_prefill_id = prefill.get("ingredient_id")
    filtered_ids = [x["id"] for x in filtered_masters]
    if selected_prefill_id in master_by_id and selected_prefill_id not in filtered_ids:
        filtered_masters.insert(0, master_by_id[selected_prefill_id])
        filtered_ids.insert(0, selected_prefill_id)
    default_index = filtered_ids.index(selected_prefill_id) if selected_prefill_id in filtered_ids else 0
    selected_id = st.selectbox(
        "식재료",
        filtered_ids,
        index=default_index,
        format_func=lambda value: format_ingredient_option(master_by_id[value]),
        key=f"ingredient_select_{generation}",
    )
    master = master_by_id[selected_id]

    expiry_toggle_key = f"use_expiry_add_{generation}"
    use_expiry = st.checkbox(
        "포장지 표시기한 입력",
        value=bool(prefill.get("expiry_date")),
        key=expiry_toggle_key,
        help="체크하면 바로 아래 입력 폼에 날짜 선택란이 나타납니다.",
    )

    with st.form(f"add_ingredient_{generation}", clear_on_submit=False):
        st.markdown("#### 기본 정보")
        c1, c2, c3 = st.columns(3)
        quantity = c1.number_input("수량", min_value=0.1, value=float(prefill.get("quantity", 1.0)), step=0.5)
        unit_options = master["common_units"] or ["개"]
        prefill_unit = prefill.get("unit")
        unit_index = unit_options.index(prefill_unit) if prefill_unit in unit_options else 0
        unit = c2.selectbox("단위", unit_options, index=unit_index)
        storage_options = ["냉장", "냉동", "실온"]
        default_storage = prefill.get("storage", master["default_storage"])
        storage = c3.selectbox("보관 위치", storage_options, index=storage_options.index(default_storage))

        d1, d2 = st.columns(2)
        purchase_date = d1.date_input("구매일", value=datetime.now(KST).date())
        expiry_default = date.fromisoformat(prefill["expiry_date"]) if prefill.get("expiry_date") else datetime.now(KST).date()
        expiry_date = d2.date_input("포장지 표시기한", value=expiry_default) if use_expiry else None
        if not use_expiry:
            d2.caption("표시기한을 입력하지 않습니다. 구매일과 식재료별 관리 구간으로 우선도를 보완 계산합니다.")

        with st.expander("상세·개봉·상태 정보 (선택)"):
            detail_name = st.text_input("상세명", value=prefill.get("detail_name", ""), placeholder="예: 찌개용 앞다리살")
            o1, o2 = st.columns(2)
            opened = o1.checkbox("개봉함", value=False)
            opened_date = o2.date_input("개봉일", value=datetime.now(KST).date())
            st.caption("식재료군별 상태 질문입니다. 하나라도 해당하면 직접 확인 대상으로 저장되고 자동 추천에서 제외됩니다.")
            condition_notes = []
            for idx, question in enumerate(master.get("condition_questions", [])):
                if st.checkbox(question, key=f"condition_{generation}_{idx}"):
                    condition_notes.append(question)
            exclude_manually = st.checkbox("이번 재고를 추천에서 일시 제외")
            priority_override = st.checkbox("사용자 지정 우선 사용")
            note = st.text_input("메모", value=prefill.get("note", ""))

        submitted = st.form_submit_button("냉장고에 저장", type="primary", use_container_width=True)
        if submitted:
            condition_status = "excluded" if exclude_manually else "needs_review" if condition_notes else "normal"
            payload = {
                "ingredient_id": selected_id,
                "detail_name": detail_name,
                "quantity": quantity,
                "unit": unit,
                "storage": storage,
                "purchase_date": purchase_date.isoformat(),
                "expiry_date": expiry_date.isoformat() if expiry_date else None,
                "opened": opened,
                "opened_date": opened_date.isoformat() if opened else None,
                "priority_override": priority_override,
                "condition_status": condition_status,
                "condition_notes": condition_notes,
                "note": note,
            }
            try:
                api_request("POST", "/ingredients", json=payload)
                invalidate_recommendation()
                st.session_state.add_prefill = None
                st.success("식재료를 저장했습니다.")
                nav_to("🧊 냉장고 현황")
            except ApiError as exc:
                show_api_error(exc)


elif st.session_state.nav == "🧂 내 양념장":
    st.subheader("내 양념장")
    st.caption("저장한 체크 상태는 다음 추천에서도 자동으로 불러옵니다.")
    try:
        seasonings = api_request("GET", "/seasonings")
    except ApiError as exc:
        show_api_error(exc)
        st.stop()
    seasoning_by_id = {x["id"]: x for x in seasonings}
    with st.form("seasoning_form"):
        selected_ids = []
        for group, ids in PANTRY_GROUPS.items():
            valid = [x for x in ids if x in seasoning_by_id]
            if not valid:
                continue
            st.markdown(f"#### {group}")
            cols = st.columns(4)
            for idx, seasoning_id in enumerate(valid):
                item = seasoning_by_id[seasoning_id]
                checked = cols[idx % 4].checkbox(item["name"], value=bool(item["owned"]), key=f"pantry_{seasoning_id}")
                if checked:
                    selected_ids.append(seasoning_id)
        ungrouped = [x for x in seasonings if x["id"] not in {i for ids in PANTRY_GROUPS.values() for i in ids}]
        if ungrouped:
            st.markdown("#### 기타")
            cols = st.columns(4)
            for idx, item in enumerate(ungrouped):
                checked = cols[idx % 4].checkbox(item["name"], value=bool(item["owned"]), key=f"pantry_{item['id']}")
                if checked:
                    selected_ids.append(item["id"])
        if st.form_submit_button("내 양념장 저장", type="primary", use_container_width=True):
            try:
                result = api_request("PUT", "/seasonings", json={"owned_ids": selected_ids})
                invalidate_recommendation()
                st.success(result["message"])
                st.rerun()
            except ApiError as exc:
                show_api_error(exc)


elif st.session_state.nav == "🍳 메뉴 추천":
    st.subheader("오늘 뭐먹지")
    try:
        inventory_data = api_request("GET", "/ingredients")
        seasonings = api_request("GET", "/seasonings")
        recent_meals = api_request("GET", "/meals/history?limit=1")
    except ApiError as exc:
        show_api_error(exc)
        st.stop()

    if not inventory_data["items"]:
        st.warning("냉장고에 식재료가 없습니다.")
        if st.button("식재료 추가로 이동"):
            nav_to("➕ 식재료 추가")
        st.stop()

    seasoning_ids = [x["id"] for x in seasonings]
    seasoning_name = {x["id"]: x["name"] for x in seasonings}
    owned_default = [x["id"] for x in seasonings if x["owned"]]
    latest_meal = recent_meals[0] if recent_meals else None

    cuisine_options = ["입력하지 않음", "한식", "중식", "일식", "양식", "기타"]
    meal_type_options = ["입력하지 않음", "밥·덮밥", "국·찌개", "면", "볶음·구이", "반찬", "간단식", "샐러드·가벼운 식사"]
    default_previous_cuisine = latest_meal.get("cuisine") if latest_meal and latest_meal.get("cuisine") in cuisine_options else "입력하지 않음"
    default_previous_type = latest_meal.get("meal_type") if latest_meal and latest_meal.get("meal_type") in meal_type_options else "입력하지 않음"

    if latest_meal:
        st.caption(f"최근 완료 메뉴를 직전 식사 기본값으로 불러왔습니다: {latest_meal['recipe_name']} · {latest_meal['cuisine']} · {latest_meal['meal_type']}")

    with st.form("recommend_form"):
        st.markdown("#### 기본 추천 조건")
        b1, b2 = st.columns(2)
        preferred_cuisine = b1.selectbox("음식 계열", ["상관없음", "한식", "중식", "일식", "양식"])
        preferred_meal_type = b2.selectbox(
            "식사 형태",
            ["상관없음", "밥·덮밥", "국·찌개", "면", "볶음·구이", "반찬", "간단식", "샐러드·가벼운 식사"],
        )

        b3, b4 = st.columns(2)
        max_minutes = b3.select_slider(
            "조리 가능 시간",
            options=[5, 15, 20, 30, 45, 60],
            value=30,
            format_func=lambda x: f"{x}분",
        )
        tools = b4.multiselect(
            "사용 가능한 조리기구 (없어도 됨)",
            ["프라이팬", "냄비", "전자레인지", "에어프라이어", "오븐"],
            default=["프라이팬", "냄비"],
            help="아무것도 선택하지 않으면 조리기구가 필요 없는 메뉴만 추천됩니다.",
        )

        with st.expander("상세 추천 설정"):
            st.markdown("##### 취향 적용")
            preference_strength = st.selectbox(
                "음식 계열 적용 강도",
                ["priority", "soft", "strict"],
                format_func=lambda x: {
                    "soft": "선호함",
                    "priority": "가능하면 해당 계열 먼저",
                    "strict": "해당 계열만 추천",
                }[x],
            )

            st.markdown("##### 직전·최근 식사 반복 조절")
            l1, l2, l3 = st.columns(3)
            previous_meal_cuisine = l1.selectbox(
                "직전 식사 음식 계열",
                cuisine_options,
                index=cuisine_options.index(default_previous_cuisine),
            )
            previous_meal_type = l2.selectbox(
                "직전 식사 형태",
                meal_type_options,
                index=meal_type_options.index(default_previous_type),
            )
            previous_meal_avoidance = l3.selectbox(
                "직전 식사 유사 메뉴 처리",
                ["soft", "none", "exclude_cuisine", "exclude_type", "exclude_either", "exclude_both"],
                format_func=lambda x: {
                    "none": "상관없음",
                    "soft": "가능하면 피하기",
                    "exclude_cuisine": "같은 음식 계열 제외",
                    "exclude_type": "같은 식사 형태 제외",
                    "exclude_either": "계열 또는 형태가 같으면 제외",
                    "exclude_both": "계열과 형태가 모두 같을 때만 제외",
                }[x],
            )

            st.markdown("##### 추천 정책")
            p1, p2 = st.columns(2)
            mode = p1.selectbox(
                "추천 성향",
                ["balanced", "fridge", "taste"],
                format_func=lambda x: {
                    "balanced": "균형",
                    "fridge": "냉장고 소진 우선",
                    "taste": "취향 우선",
                }[x],
            )
            repeat = p2.selectbox(
                "최근 완료 메뉴 반복 회피",
                ["medium", "low", "high"],
                format_func=lambda x: {"medium": "보통", "low": "낮음", "high": "높음"}[x],
            )
            allow_substitutions = st.checkbox(
                "비슷한 재료·양념 대체 허용",
                value=True,
                help="정확 일치를 먼저 사용하고, 남은 조건에만 동등 대체를 적용합니다. 간이 대체는 완전 충족으로 계산하지 않습니다.",
            )

            st.markdown("##### 이번 추천의 양념 보유 상태")
            temporary_owned = st.multiselect(
                "사용 가능한 양념",
                seasoning_ids,
                default=owned_default,
                format_func=lambda x: seasoning_name[x],
            )
            save_pantry = st.checkbox("현재 선택을 내 양념장에도 저장")

        submitted = st.form_submit_button("메뉴 추천 받기", type="primary", use_container_width=True)
        if submitted:
            try:
                if save_pantry:
                    api_request("PUT", "/seasonings", json={"owned_ids": temporary_owned})
                    invalidate_recommendation()
                result = api_request(
                    "POST",
                    "/recommend",
                    json={
                        "preferred_cuisine": preferred_cuisine,
                        "cuisine_preference_strength": preference_strength,
                        "preferred_meal_type": preferred_meal_type,
                        "previous_meal_cuisine": previous_meal_cuisine,
                        "previous_meal_type": previous_meal_type,
                        "previous_meal_avoidance": previous_meal_avoidance,
                        "max_cooking_minutes": max_minutes,
                        "appliances": tools,
                        "recommendation_mode": mode,
                        "repeat_avoidance": repeat,
                        "temporary_owned_seasoning_ids": temporary_owned,
                        "excluded_ingredient_ids": [],
                        "allow_substitutions": allow_substitutions,
                    },
                )
                st.session_state.recommendation_result = result
                st.session_state.selected_recipe = None
            except ApiError as exc:
                show_api_error(exc)

    result = st.session_state.recommendation_result
    if result:
        summary = result.get("request_summary", {})
        if summary:
            st.markdown(
                f"""
                <div class="summary-box"><b>선택한 조건</b><br>
                음식 계열: {summary.get('preferred_cuisine')} ({summary.get('cuisine_preference_strength')}) ·
                식사 형태: {summary.get('preferred_meal_type')} · 직전 식사 처리: {summary.get('previous_meal_avoidance')} ·
                시간: {summary.get('max_cooking_minutes')}분 · 도구: {', '.join(summary.get('appliances', [])) or '필요 없음'}</div>
                """,
                unsafe_allow_html=True,
            )

        if result["status"] != "ok":
            st.warning(result["message"])
            for suggestion in result.get("suggestions", []):
                st.write(f"- {suggestion}")
            render_diagnostics(result)
        else:
            policy = result["scoring_policy"]
            weight_labels = {
                "priority": "우선 재료",
                "completeness": "재료·양념",
                "taste": "현재 취향",
                "diversity": "식사 다양성",
                "convenience": "조리 편의",
            }
            weight_text = " · ".join(f"{weight_labels[k]} {v}점" for k, v in policy["weights"].items())
            st.caption(f"{policy['mode_label']} 모드 · {weight_text}")
            st.caption(policy["note"])
            st.caption(
                "선택 조건에 맞는 결과 그룹을 먼저 표시합니다. 추천 점수는 각 그룹 안에서 메뉴 순서를 정하는 상대 점수이므로, "
                "냉장고 재료 활용도가 높은 다른 계열 메뉴의 점수가 더 높을 수 있습니다."
            )
            render_diagnostics(result)

            cuisine_label = summary.get("preferred_cuisine", "상관없음")
            type_label = summary.get("preferred_meal_type", "상관없음")
            exact_label = "선택 조건" if cuisine_label == "상관없음" and type_label == "상관없음" else "·".join(x for x in [cuisine_label, type_label] if x != "상관없음")

            priority_results = result.get("priority_override_results", [])
            priority_one_more = result.get("priority_override_one_more_results", [])
            if priority_results or priority_one_more:
                st.markdown("### 사용자 지정 우선 재료 활용 메뉴")
                st.caption(
                    "직접 '우선 사용'으로 지정한 식재료를 포함하면서 현재 시간·조리기구 조건을 통과한 메뉴를 가장 먼저 표시합니다."
                )
                for rank, recipe in enumerate(priority_results, start=1):
                    render_recipe_card(recipe, rank, "priority_override")
                if priority_one_more:
                    st.markdown("#### 우선 재료 활용 · 하나만 더 있으면 가능해요")
                    for rank, recipe in enumerate(priority_one_more, start=1):
                        render_one_more(recipe, rank, "priority_override_one")

            exact = result.get("preferred_exact_results", [])
            st.markdown(f"### {exact_label}로 바로 만들 수 있어요")
            priority_exact_exists = any(
                item.get("is_preferred_cuisine") and item.get("is_preferred_meal_type")
                for item in priority_results
            )
            if not exact and priority_exact_exists:
                st.caption("완전 일치하는 우선 사용 메뉴는 위의 '사용자 지정 우선 재료 활용 메뉴'에 먼저 표시했습니다.")
            elif not exact:
                st.info("현재 재고와 조리 조건을 모두 만족하는 완전 일치 메뉴가 없습니다.")
            for rank, recipe in enumerate(exact, start=1):
                render_recipe_card(recipe, rank, "preferred_exact")

            exact_one = result.get("preferred_exact_one_more_results", [])
            if exact_one:
                st.markdown(f"### {exact_label} · 하나만 더 있으면 가능해요")
                for rank, recipe in enumerate(exact_one, start=1):
                    render_one_more(recipe, rank, "preferred_exact_one")

            same_cuisine_other = result.get("preferred_other_type_results", [])
            if same_cuisine_other:
                st.markdown("### 같은 음식 계열이지만 다른 식사 형태")
                st.caption("음식 계열은 맞지만 선택한 식사 형태와 달라 별도 구역에 표시합니다.")
                for rank, recipe in enumerate(same_cuisine_other, start=1):
                    render_recipe_card(recipe, rank, "preferred_other_type")

            same_cuisine_other_one = result.get("preferred_other_type_one_more_results", [])
            if same_cuisine_other_one:
                st.markdown("### 같은 계열·다른 형태 · 하나만 더 있으면 가능해요")
                for rank, recipe in enumerate(same_cuisine_other_one, start=1):
                    render_one_more(recipe, rank, "preferred_other_type_one")

            alt_exact = result.get("alternative_exact_results", [])
            if alt_exact:
                st.markdown("### 다른 음식 계열이지만 원하는 식사 형태")
                st.caption("음식 계열은 다르지만 선택한 식사 형태와 냉장고 활용도가 좋은 메뉴입니다.")
                for rank, recipe in enumerate(alt_exact, start=1):
                    render_recipe_card(recipe, rank, "alternative_exact")

            alt_other = result.get("alternative_other_type_results", [])
            if alt_other:
                st.markdown("### 조건을 완화한 대체 추천")
                for rank, recipe in enumerate(alt_other, start=1):
                    render_recipe_card(recipe, rank, "alternative_other")

            alt_exact_one = result.get("alternative_exact_one_more_results", [])
            alt_other_one = result.get("alternative_other_type_one_more_results", [])
            if alt_exact_one or alt_other_one:
                st.markdown("### 다른 계열 · 하나만 더 있으면 가능해요")
                for rank, recipe in enumerate(alt_exact_one + alt_other_one, start=1):
                    render_one_more(recipe, rank, "alternative_one")

    selected_recipe = st.session_state.selected_recipe
    if selected_recipe:
        st.markdown('<div id="meal-completion"></div>', unsafe_allow_html=True)
        if st.session_state.get("scroll_to_completion"):
            components.html(
                """
                <script>
                const target = window.parent.document.getElementById('meal-completion');
                if (target) {
                  setTimeout(() => target.scrollIntoView({behavior: 'smooth', block: 'start'}), 150);
                }
                </script>
                """,
                height=0,
            )
            st.session_state.scroll_to_completion = False
        st.divider()
        st.markdown(f"### 재고 반영 · {selected_recipe['name']}")
        st.caption("실제로 사용한 냉장고 재료와 사용량을 선택하면 해당 구매 묶음의 재고만 차감합니다.")
        with st.form("complete_meal_form"):
            usage_payload = []
            for lot in selected_recipe["matched_inventory"]:
                label = f"{lot['name']} · 현재 {lot['quantity']:g} {lot['unit']}"
                if lot.get("used_as") and lot["used_as"] != lot["name"]:
                    label += f" · {lot['used_as']} 용도"
                mode_key = f"usage_mode_{selected_recipe['recipe_id']}_{lot['inventory_id']}"
                use_mode = st.selectbox(
                    label,
                    ["사용하지 않음", "전부 사용", "일부 사용"],
                    key=mode_key,
                )
                partial_default = max(float(lot["quantity"]) / 2.0, 0.0)
                partial_used = st.number_input(
                    f"일부 사용 시 사용한 양 ({lot['unit']})",
                    min_value=0.0,
                    max_value=float(lot["quantity"]),
                    value=partial_default,
                    step=max(min(float(lot["quantity"]) / 10.0, 1.0), 0.1),
                    key=f"partial_used_{selected_recipe['recipe_id']}_{lot['inventory_id']}",
                    help="'일부 사용'을 선택한 경우에만 이 값이 재고 차감에 반영됩니다.",
                )
                if use_mode == "사용하지 않음":
                    remaining = float(lot["quantity"])
                elif use_mode == "전부 사용":
                    remaining = 0.0
                else:
                    remaining = max(float(lot["quantity"]) - float(partial_used), 0.0)
                usage_payload.append(
                    {
                        "inventory_id": lot["inventory_id"],
                        "remaining_quantity": remaining,
                        "use_mode": use_mode,
                        "used_quantity": float(lot["quantity"]) - remaining,
                        "original_quantity": float(lot["quantity"]),
                        "name": lot["name"],
                    }
                )
            if st.form_submit_button("재고에 반영하기", type="primary"):
                partial_errors = [
                    row["name"]
                    for row in usage_payload
                    if row["use_mode"] == "일부 사용"
                    and (row["used_quantity"] <= 0 or row["used_quantity"] >= row["original_quantity"])
                ]
                if partial_errors:
                    st.error("일부 사용은 0보다 크고 현재 수량보다 작은 사용량을 입력해야 합니다: " + ", ".join(partial_errors))
                elif not any(row["used_quantity"] > 0 for row in usage_payload):
                    st.error("최소 한 개의 재료를 전부 또는 일부 사용으로 선택해주세요.")
                else:
                    try:
                        api_usage = [
                            {
                                "inventory_id": row["inventory_id"],
                                "remaining_quantity": row["remaining_quantity"],
                            }
                            for row in usage_payload
                        ]
                        response = api_request(
                            "POST",
                            "/meals/complete",
                            json={
                                "recipe_id": selected_recipe["recipe_id"],
                                "eaten_at": datetime.now(KST).isoformat(timespec="seconds"),
                                "meal_slot": meal_slot_now(),
                                "usage": api_usage,
                                "note": "",
                            },
                        )
                        completion_result = {
                            "message": response["message"],
                            "recipe_name": selected_recipe["name"],
                            "usage": response.get("usage", []),
                        }
                        invalidate_recommendation()
                        st.session_state.completion_result = completion_result
                        st.session_state.scroll_to_completion_result = True
                        st.rerun()
                    except ApiError as exc:
                        show_api_error(exc)


    completion_result = st.session_state.get("completion_result")
    if completion_result:
        st.markdown('<div id="stock-completion-result"></div>', unsafe_allow_html=True)
        if st.session_state.get("scroll_to_completion_result"):
            components.html(
                """
                <script>
                const target = window.parent.document.getElementById('stock-completion-result');
                if (target) {
                  setTimeout(() => target.scrollIntoView({behavior: 'smooth', block: 'start'}), 150);
                }
                </script>
                """,
                height=0,
            )
            st.session_state.scroll_to_completion_result = False
        st.markdown(
            f'<div class="completion-box"><h3>✅ 재고 반영 완료</h3>'
            f'<p><b>{completion_result["recipe_name"]}</b> 조리에 사용한 재료를 냉장고 재고에 반영했습니다.</p></div>',
            unsafe_allow_html=True,
        )
        for row in completion_result.get("usage", []):
            st.write(
                f"- {row['name']}: {row['used_quantity']:g} {row['unit']} 사용 · "
                f"{row['remaining_quantity']:g} {row['unit']} 남음"
            )
        st.caption("같은 메뉴의 연속 추천을 줄이기 위한 최소 완료 이력은 내부적으로만 저장됩니다.")
        cr1, cr2 = st.columns(2)
        if cr1.button("냉장고 현황 보기", use_container_width=True, type="primary"):
            st.session_state.completion_result = None
            nav_to("🧊 냉장고 현황")
        if cr2.button("메뉴 다시 추천받기", use_container_width=True):
            st.session_state.completion_result = None
            st.rerun()

