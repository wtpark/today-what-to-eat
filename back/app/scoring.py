from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from .constants import (
    CUISINE_PREFERENCE_LABELS,
    MODE_LABELS,
    MODE_WEIGHTS,
    PREVIOUS_MEAL_AVOIDANCE_LABELS,
    REPEAT_HALF_LIFE,
)
from .substitutions import ingredient_candidates, seasoning_candidates

KST = ZoneInfo("Asia/Seoul")


def today_kst() -> date:
    return datetime.now(KST).date()


def now_kst() -> datetime:
    return datetime.now(KST)


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _explicit_expiry_points(expiry_date: date | None, today: date) -> tuple[float, str, bool]:
    if expiry_date is None:
        return 0.0, "표시기한 미입력", False
    days = (expiry_date - today).days
    if days < 0:
        return 0.0, f"표시기한 {abs(days)}일 경과", True
    if days == 0:
        return 50.0, "표시기한 오늘", False
    if days == 1:
        return 45.0, "표시기한 1일 남음", False
    if days <= 3:
        return 35.0, f"표시기한 {days}일 남음", False
    if days <= 7:
        return 20.0, f"표시기한 {days}일 남음", False
    if days <= 14:
        return 10.0, f"표시기한 {days}일 남음", False
    return 0.0, f"표시기한 {days}일 남음", False


def _freshness_points(item: dict[str, Any], today: date) -> tuple[float, str, bool]:
    """Estimate management priority only when the package date is absent.

    This is not a food-safety or edible-until decision. The master-data window is a
    project policy that controls FIFO priority for produce and other undated items.
    """
    purchase = _parse_date(item.get("purchase_date")) or today
    elapsed = max((today - purchase).days, 0)
    window = max(int(item.get("freshness_window_days") or 14), 1)
    ratio = min(elapsed / window, 1.0)
    points = 40.0 * ratio
    due = elapsed >= window
    return points, f"표시기한 미입력 · 관리 구간 {window}일 중 {elapsed}일 경과", due


def _opened_points(item: dict[str, Any], today: date) -> tuple[float, str]:
    if not item.get("opened"):
        return 0.0, "미개봉"
    opened_date = _parse_date(item.get("opened_date")) or _parse_date(item.get("purchase_date")) or today
    elapsed = max((today - opened_date).days, 0)
    window = max(int(item.get("opened_window_days") or 1), 1)
    # Opening itself raises management priority; elapsed time adds the remaining points.
    points = 5.0 + 15.0 * min(elapsed / window, 1.0)
    return min(points, 20.0), f"개봉 상태 · 개봉 후 {elapsed}일 / 관리 구간 {window}일"


def _confidence(item: dict[str, Any]) -> tuple[str, str]:
    has_purchase = bool(item.get("purchase_date"))
    has_expiry = bool(item.get("expiry_date"))
    has_open = (not item.get("opened")) or bool(item.get("opened_date"))
    if has_purchase and has_expiry and has_open:
        return "높음", "구매일·표시기한·개봉 정보가 입력됨"
    if has_purchase and has_open:
        return "보통", "표시기한이 없어 식재료별 관리 구간으로 보완 계산"
    return "낮음", "입력 정보가 부족해 점수 해석에 주의 필요"


def enrich_inventory_priority(items: list[dict[str, Any]], today: date | None = None) -> list[dict[str, Any]]:
    today = today or today_kst()
    by_ingredient: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        by_ingredient[item["ingredient_id"]].append(item)

    # Same-day purchases receive the same FIFO component because purchase time is not stored.
    fifo_relative: dict[int, float] = {}
    for group in by_ingredient.values():
        unique_dates = sorted({item["purchase_date"] for item in group})
        date_scores: dict[str, float] = {}
        for idx, purchase_date in enumerate(unique_dates):
            date_scores[purchase_date] = (
                10.0 * (1 - idx / (len(unique_dates) - 1)) if len(unique_dates) > 1 else 0.0
            )
        for item in group:
            fifo_relative[item["id"]] = date_scores[item["purchase_date"]]

    enriched: list[dict[str, Any]] = []
    for raw in items:
        item = dict(raw)
        purchase = _parse_date(item.get("purchase_date")) or today
        age_days = max((today - purchase).days, 0)
        age_points = 10.0 * min(age_days / 14.0, 1.0)
        fifo_points = min(20.0, age_points + fifo_relative.get(item["id"], 0.0))

        explicit_expiry = _parse_date(item.get("expiry_date"))
        expired = False
        freshness_due = False
        if explicit_expiry:
            date_points, date_reason, expired = _explicit_expiry_points(explicit_expiry, today)
            date_source = "포장지 표시기한"
        else:
            date_points, date_reason, freshness_due = _freshness_points(item, today)
            date_source = "식재료별 관리 구간 추정"

        opened_points, opened_reason = _opened_points(item, today)
        sensitivity_points = 10.0 * max(
            min((int(item.get("perishability_level", 1)) - 1) / 4.0, 1.0), 0.0
        )

        storage_factor = 0.35 if item.get("storage") == "냉동" else 1.0
        storage_reason = None
        if storage_factor < 1.0:
            date_points *= storage_factor
            opened_points *= storage_factor
            fifo_points *= storage_factor
            sensitivity_points *= storage_factor
            storage_reason = "냉동 보관으로 우선도 구성 점수에 35% 보정 적용"
            freshness_due = False

        score = round(min(date_points + opened_points + fifo_points + sensitivity_points, 100.0), 1)
        ranking_score = 100.0 if item.get("priority_override") else score
        condition_status = item.get("condition_status", "normal")
        quantity = float(item.get("quantity", 0) or 0)
        recommendation_eligible = condition_status == "normal" and not expired and quantity > 0

        if quantity <= 0:
            action = "수량 없음"
        elif expired:
            action = "표시기한 경과 · 사용자 확인 필요"
        elif condition_status == "needs_review":
            action = "상태 확인 필요 · 추천 제외"
        elif condition_status == "excluded":
            action = "사용자가 추천에서 제외"
        elif item.get("priority_override"):
            action = "사용자 지정 우선 사용"
        elif freshness_due or (explicit_expiry and 0 <= (explicit_expiry - today).days <= 1) or score >= 65:
            action = "먼저 사용"
        elif score >= 35:
            action = "이번 주 사용"
        else:
            action = "여유"

        confidence, confidence_reason = _confidence(item)
        item.update(
            {
                "priority_score": score,
                "ranking_priority_score": ranking_score,
                "priority_override": bool(item.get("priority_override")),
                "expired": expired,
                "freshness_due": freshness_due,
                "date_score_source": date_source,
                "recommendation_eligible": recommendation_eligible,
                "action": action,
                "confidence": confidence,
                "confidence_reason": confidence_reason,
                "priority_breakdown": {
                    "표시기한·관리 구간": round(date_points, 1),
                    "개봉 후 경과도": round(opened_points, 1),
                    "선입선출·구매 경과": round(fifo_points, 1),
                    "식품군 소비 민감도": round(sensitivity_points, 1),
                },
                "priority_reasons": [
                    reason
                    for reason in [date_reason, opened_reason, f"구매 후 {age_days}일 경과", storage_reason]
                    if reason
                ],
            }
        )
        enriched.append(item)

    enriched.sort(
        key=lambda x: (
            not x["priority_override"],
            not x["recommendation_eligible"],
            -x["ranking_priority_score"],
            x["purchase_date"],
        )
    )
    return enriched


def _owned_seasoning_ids(seasonings: list[dict[str, Any]], override_ids: list[str] | None) -> set[str]:
    if override_ids is not None:
        return set(override_ids)
    return {item["id"] for item in seasonings if item.get("owned")}


def _previous_values(request: dict[str, Any]) -> tuple[str, str, str]:
    return (
        request.get("previous_meal_cuisine", "입력하지 않음"),
        request.get("previous_meal_type", "입력하지 않음"),
        request.get("previous_meal_avoidance", "soft"),
    )


def _hard_previous_exclusion(recipe: dict[str, Any], request: dict[str, Any]) -> str | None:
    cuisine, meal_type, mode = _previous_values(request)
    same_cuisine = cuisine != "입력하지 않음" and cuisine == recipe["cuisine"]
    same_type = meal_type != "입력하지 않음" and meal_type == recipe["meal_type"]
    if mode == "exclude_cuisine" and same_cuisine:
        return "직전 식사와 같은 음식 계열 제외"
    if mode == "exclude_type" and same_type:
        return "직전 식사와 같은 식사 형태 제외"
    if mode == "exclude_either" and (same_cuisine or same_type):
        return "직전 식사와 계열 또는 식사 형태가 같아 제외"
    if mode == "exclude_both" and same_cuisine and same_type:
        return "직전 식사와 계열·형태가 모두 같아 제외"
    return None


def _manual_previous_already_in_history(
    history: list[dict[str, Any]], request: dict[str, Any], now: datetime
) -> bool:
    cuisine, meal_type, _ = _previous_values(request)
    if not history or (cuisine == "입력하지 않음" and meal_type == "입력하지 않음"):
        return False
    latest = history[0]
    try:
        eaten = datetime.fromisoformat(latest["eaten_at"])
        if eaten.tzinfo is None:
            eaten = eaten.replace(tzinfo=KST)
        hours = max((now - eaten.astimezone(KST)).total_seconds() / 3600.0, 0.0)
    except (ValueError, TypeError):
        return False
    if hours > 12:
        return False
    cuisine_match = cuisine == "입력하지 않음" or latest.get("cuisine") == cuisine
    type_match = meal_type == "입력하지 않음" or latest.get("meal_type") == meal_type
    return cuisine_match and type_match


def _diversity_ratio(
    recipe: dict[str, Any], history: list[dict[str, Any]], request: dict[str, Any], now: datetime
) -> tuple[float, list[str]]:
    half_life = REPEAT_HALF_LIFE[request["repeat_avoidance"]]
    penalty = 0.0
    reasons: list[str] = []
    for meal in history:
        try:
            eaten = datetime.fromisoformat(meal["eaten_at"])
            if eaten.tzinfo is None:
                eaten = eaten.replace(tzinfo=KST)
            elapsed_days = max((now - eaten.astimezone(KST)).total_seconds() / 86400.0, 0.0)
        except (ValueError, TypeError):
            continue
        decay = 2 ** (-elapsed_days / half_life)
        local_penalty = 0.0
        if meal["recipe_id"] == recipe["id"]:
            local_penalty += 0.60
        else:
            if meal["cuisine"] == recipe["cuisine"]:
                local_penalty += 0.15
            if meal["meal_type"] == recipe["meal_type"]:
                local_penalty += 0.15
            if meal["cooking_method"] == recipe["cooking_method"]:
                local_penalty += 0.10
        penalty += local_penalty * decay

    cuisine, meal_type, avoidance = _previous_values(request)
    if avoidance == "soft" and not _manual_previous_already_in_history(history, request, now):
        if cuisine != "입력하지 않음" and cuisine == recipe["cuisine"]:
            penalty += 0.25
            reasons.append("직전 식사와 같은 음식 계열이라 다양성 점수가 낮아짐")
        if meal_type != "입력하지 않음" and meal_type == recipe["meal_type"]:
            penalty += 0.20
            reasons.append("직전 식사와 같은 식사 형태라 다양성 점수가 낮아짐")

    ratio = max(0.0, 1.0 - min(penalty, 1.0))
    if not reasons and ratio >= 0.8:
        reasons.append("최근 식사와의 중복이 적음")
    return ratio, reasons


def _match_ingredient(
    required: dict[str, Any],
    available_ids: set[str],
    used_actual_ids: set[str],
    allow_substitutions: bool,
    recipe: dict[str, Any],
) -> dict[str, Any] | None:
    candidates = (
        ingredient_candidates(required["ingredient_id"], recipe)
        if allow_substitutions
        else [{"id": required["ingredient_id"], "quality": 1.0, "tier": "exact", "warning": None}]
    )
    for candidate in candidates:
        actual_id = candidate["id"]
        if actual_id in available_ids and actual_id not in used_actual_ids:
            return {
                "canonical_id": required["ingredient_id"],
                "canonical_name": required["name"],
                "actual_id": actual_id,
                "quality": candidate["quality"],
                "tier": candidate.get("tier", "equivalent"),
                "warning": candidate.get("warning"),
                "role": required["role"],
                "weight": float(required["weight"]),
            }
    return None


def _match_seasoning(
    seasoning: dict[str, Any], owned_ids: set[str], allow_substitutions: bool, recipe: dict[str, Any]
) -> dict[str, Any] | None:
    candidates = (
        seasoning_candidates(seasoning["seasoning_id"], recipe)
        if allow_substitutions
        else [{"id": seasoning["seasoning_id"], "quality": 1.0, "tier": "exact", "warning": None}]
    )
    for candidate in candidates:
        if candidate["id"] in owned_ids:
            return {
                "canonical_id": seasoning["seasoning_id"],
                "canonical_name": seasoning["name"],
                "actual_id": candidate["id"],
                "quality": candidate["quality"],
                "tier": candidate.get("tier", "equivalent"),
                "warning": candidate.get("warning"),
                "required": bool(seasoning["required"]),
            }
    return None


def _tool_requirements_satisfied(requirements: list[Any], selected_tools: set[str]) -> bool:
    for requirement in requirements:
        if isinstance(requirement, str):
            if requirement not in selected_tools:
                return False
        elif isinstance(requirement, list):
            if not set(requirement).intersection(selected_tools):
                return False
        else:
            return False
    return True


def _tool_requirements_label(requirements: list[Any]) -> str:
    if not requirements:
        return "별도 조리기구 없이"
    labels: list[str] = []
    for requirement in requirements:
        labels.append(" 또는 ".join(requirement) if isinstance(requirement, list) else str(requirement))
    return " · ".join(labels)


def _taste_ratio(recipe: dict[str, Any], request: dict[str, Any]) -> float:
    preferred_cuisine = request["preferred_cuisine"]
    strength = request.get("cuisine_preference_strength", "priority")
    if preferred_cuisine == "상관없음":
        cuisine_ratio = 1.0
    elif recipe["cuisine"] == preferred_cuisine:
        cuisine_ratio = 1.0
    else:
        cuisine_ratio = {"soft": 0.35, "priority": 0.10, "strict": 0.0}[strength]

    preferred_type = request["preferred_meal_type"]
    if preferred_type == "상관없음":
        type_ratio = 1.0
    elif recipe["meal_type"] == preferred_type:
        type_ratio = 1.0
    else:
        type_ratio = 0.0
    return 0.65 * cuisine_ratio + 0.35 * type_ratio


def _missing_units(missing_groups: list[dict[str, Any]]) -> int:
    return sum(max(int(item.get("needed_count", 1)), 1) for item in missing_groups)


def _evaluate_recipe(
    recipe: dict[str, Any],
    inventory_by_ingredient: dict[str, list[dict[str, Any]]],
    owned_seasonings: set[str],
    top_priority_ids: set[str],
    top_priority_denominator: float,
    meal_history: list[dict[str, Any]],
    request: dict[str, Any],
    seasoning_names: dict[str, str],
    now: datetime,
) -> tuple[dict[str, Any] | None, str | None, list[dict[str, Any]]]:
    preferred_cuisine = request["preferred_cuisine"]
    is_preferred = preferred_cuisine == "상관없음" or recipe["cuisine"] == preferred_cuisine

    if request.get("cuisine_preference_strength") == "strict" and not is_preferred:
        return None, "strict_cuisine", []

    previous_exclusion = _hard_previous_exclusion(recipe, request)
    if previous_exclusion:
        return None, "previous_meal", []

    if recipe["cook_time"] > request["max_cooking_minutes"]:
        return None, "time", []
    selected_tools = set(request.get("appliances", []))
    if not _tool_requirements_satisfied(recipe.get("tools", []), selected_tools):
        return None, "tools", []

    available_ids = set(inventory_by_ingredient)
    allow_substitutions = bool(request.get("allow_substitutions", True))
    used_actual_ids: set[str] = set()
    substitutions_used: list[str] = []
    substitution_warnings: list[str] = []

    must = [x for x in recipe["ingredients"] if x["role"] == "must"]
    core = [x for x in recipe["ingredients"] if x["role"] == "core"]
    supporting = [x for x in recipe["ingredients"] if x["role"] == "supporting"]

    matched_must: list[dict[str, Any]] = []
    missing_groups: list[dict[str, Any]] = []
    for requirement in must:
        match = _match_ingredient(requirement, available_ids, used_actual_ids, allow_substitutions, recipe)
        if match:
            used_actual_ids.add(match["actual_id"])
            matched_must.append(match)
            if match["tier"] == "rough":
                missing_groups.append(
                    {"type": "ingredient", "id": requirement["ingredient_id"], "name": requirement["name"]}
                )
        else:
            missing_groups.append(
                {"type": "ingredient", "id": requirement["ingredient_id"], "name": requirement["name"]}
            )

    matched_core: list[dict[str, Any]] = []
    for requirement in core:
        match = _match_ingredient(requirement, available_ids, used_actual_ids, allow_substitutions, recipe)
        if match:
            used_actual_ids.add(match["actual_id"])
            matched_core.append(match)
    valid_core_count = sum(1 for m in matched_core if m["tier"] != "rough")
    core_needed = max(int(recipe.get("min_core_count", 0)) - valid_core_count, 0)
    if core_needed:
        missing_names = [
            x["name"] for x in core if x["ingredient_id"] not in {m["canonical_id"] for m in matched_core if m["tier"] != "rough"}
        ]
        missing_groups.append(
            {
                "type": "core_option",
                "id": "core_option",
                "name": " 또는 ".join(missing_names),
                "needed_count": core_needed,
            }
        )

    matched_supporting: list[dict[str, Any]] = []
    for requirement in supporting:
        match = _match_ingredient(requirement, available_ids, used_actual_ids, allow_substitutions, recipe)
        if match:
            used_actual_ids.add(match["actual_id"])
            matched_supporting.append(match)

    matched_seasonings: list[dict[str, Any]] = []
    missing_optional_seasonings: list[str] = []
    for seasoning in recipe["seasonings"]:
        match = _match_seasoning(seasoning, owned_seasonings, allow_substitutions, recipe)
        if match:
            matched_seasonings.append(match)
            if seasoning["required"] and match["tier"] == "rough":
                missing_groups.append(
                    {"type": "seasoning", "id": seasoning["seasoning_id"], "name": seasoning["name"]}
                )
        elif seasoning["required"]:
            missing_groups.append(
                {"type": "seasoning", "id": seasoning["seasoning_id"], "name": seasoning["name"]}
            )
        else:
            missing_optional_seasonings.append(seasoning["name"])

    if _missing_units(missing_groups) > 1:
        return None, "missing_many", missing_groups

    all_matches = matched_must + matched_core + matched_supporting
    ingredient_name_by_id = {
        ingredient_id: lots[0]["ingredient_name"] for ingredient_id, lots in inventory_by_ingredient.items()
    }
    for match in all_matches:
        if match["actual_id"] != match["canonical_id"]:
            substitutions_used.append(
                f"{match['canonical_name']} 대신 {ingredient_name_by_id.get(match['actual_id'], match['actual_id'])} 사용"
            )
            if match.get("warning"):
                substitution_warnings.append(match["warning"])
    for match in matched_seasonings:
        if match["actual_id"] != match["canonical_id"]:
            substitutions_used.append(
                f"{match['canonical_name']} 대신 {seasoning_names.get(match['actual_id'], match['actual_id'])} 사용"
            )
            if match.get("warning"):
                substitution_warnings.append(match["warning"])

    matched_actual_ids = {match["actual_id"] for match in all_matches}
    priority_numerator = sum(
        max(lot["ranking_priority_score"] for lot in inventory_by_ingredient[ingredient_id])
        for ingredient_id in matched_actual_ids
        if ingredient_id in top_priority_ids
    )
    priority_ratio = min(priority_numerator / top_priority_denominator, 1.0)

    ingredient_denominator = (
        sum(float(x["weight"]) for x in must)
        + 2.0 * int(recipe.get("min_core_count", 0))
        + sum(float(x["weight"]) for x in supporting)
    )
    ingredient_numerator = sum(m["weight"] * m["quality"] for m in matched_must)
    ingredient_numerator += sum(
        2.0 * m["quality"] for m in matched_core if m["tier"] != "rough"
    )
    ingredient_numerator += sum(m["weight"] * m["quality"] for m in matched_supporting)
    ingredient_ratio = min(ingredient_numerator / ingredient_denominator, 1.0) if ingredient_denominator else 1.0

    pantry_denominator = sum(2.0 if s["required"] else 0.5 for s in recipe["seasonings"])
    pantry_numerator = sum((2.0 if s["required"] else 0.5) * s["quality"] for s in matched_seasonings)
    pantry_ratio = min(pantry_numerator / pantry_denominator, 1.0) if pantry_denominator else 1.0
    completeness_ratio = 0.82 * ingredient_ratio + 0.18 * pantry_ratio

    taste_ratio = _taste_ratio(recipe, request)
    diversity_ratio, diversity_reasons = _diversity_ratio(recipe, meal_history, request, now)
    time_ratio = recipe["cook_time"] / request["max_cooking_minutes"]
    time_fit = 1.0 if time_ratio <= 0.5 else 0.82 if time_ratio <= 0.75 else 0.65
    tool_fit = 1.0 if len(recipe.get("tools", [])) <= 1 else 0.85
    convenience_ratio = 0.7 * time_fit + 0.3 * tool_fit

    weights = MODE_WEIGHTS[request["recommendation_mode"]]
    ratios = {
        "priority": priority_ratio,
        "completeness": completeness_ratio,
        "taste": taste_ratio,
        "diversity": diversity_ratio,
        "convenience": convenience_ratio,
    }
    breakdown = {key: round(ratios[key] * weights[key], 1) for key in weights}
    total = round(sum(breakdown.values()), 1)
    if missing_groups:
        total = round(max(total - 8.0, 0.0), 1)
        breakdown["missing_penalty"] = -8.0

    matched_inventory: list[dict[str, Any]] = []
    for actual_id in matched_actual_ids:
        lots = sorted(
            inventory_by_ingredient[actual_id],
            key=lambda x: (-x["ranking_priority_score"], x["purchase_date"], x["id"]),
        )
        lot = lots[0]
        canonical_names = sorted({m["canonical_name"] for m in all_matches if m["actual_id"] == actual_id})
        matched_inventory.append(
            {
                "inventory_id": lot["id"],
                "ingredient_id": actual_id,
                "name": lot["ingredient_name"],
                "used_as": ", ".join(canonical_names),
                "quantity": lot["quantity"],
                "unit": lot["unit"],
                "priority_score": lot["priority_score"],
                "priority_override": lot["priority_override"],
            }
        )
    matched_inventory.sort(key=lambda x: (not x["priority_override"], -x["priority_score"]))

    matched_supporting_canonical = {m["canonical_id"] for m in matched_supporting}
    optional_missing_ingredients = [
        x["name"] for x in supporting if x["ingredient_id"] not in matched_supporting_canonical
    ]

    reasons: list[str] = []
    override_used = [x["name"] for x in matched_inventory if x.get("priority_override")]
    urgent_used = [x["name"] for x in matched_inventory if x["priority_score"] >= 40]
    if override_used:
        reasons.append(f"직접 우선 지정한 {', '.join(override_used[:3])}을 활용합니다.")
    elif urgent_used:
        reasons.append(f"소비 우선도가 높은 {', '.join(urgent_used[:3])}을 활용합니다.")
    reasons.append(
        f"냉장고 재료 {round(ingredient_ratio * 100)}%, 저장된 양념 {round(pantry_ratio * 100)}%를 충족합니다."
    )
    if recipe["cuisine"] == preferred_cuisine and preferred_cuisine != "상관없음":
        reasons.append(f"선택한 음식 계열인 {preferred_cuisine}과 일치합니다.")
    elif preferred_cuisine != "상관없음":
        reasons.append(f"선택한 {preferred_cuisine} 대신 현재 재고 활용도가 높은 {recipe['cuisine']} 대체 메뉴입니다.")
    if recipe["meal_type"] == request["preferred_meal_type"] and request["preferred_meal_type"] != "상관없음":
        reasons.append(f"원하는 식사 형태인 {recipe['meal_type']}과 일치합니다.")
    reasons.extend(diversity_reasons)
    reasons.append(f"{recipe['cook_time']}분 안에 {_tool_requirements_label(recipe.get('tools', []))} 조리할 수 있습니다.")

    result = {
        "recipe_id": recipe["id"],
        "name": recipe["name"],
        "cuisine": recipe["cuisine"],
        "meal_type": recipe["meal_type"],
        "cooking_method": recipe["cooking_method"],
        "cook_time": recipe["cook_time"],
        "tools": recipe["tools"],
        "score": total,
        "mode": request["recommendation_mode"],
        "mode_label": MODE_LABELS[request["recommendation_mode"]],
        "score_breakdown": breakdown,
        "score_weights": weights,
        "score_details": {
            "ingredient_coverage": round(ingredient_ratio * 100),
            "pantry_coverage": round(pantry_ratio * 100),
            "substitution_count": len(substitutions_used),
        },
        "reasons": reasons,
        "matched_inventory": matched_inventory,
        "optional_missing_ingredients": optional_missing_ingredients,
        "optional_missing_seasonings": missing_optional_seasonings,
        "missing_to_make": missing_groups,
        "missing_units": _missing_units(missing_groups),
        "substitutions_used": substitutions_used,
        "substitution_warnings": list(dict.fromkeys(substitution_warnings)),
        "source": recipe.get("source", ""),
        "image_path": recipe.get("image_path"),
        "is_preferred_cuisine": is_preferred,
        "is_preferred_meal_type": request["preferred_meal_type"] == "상관없음" or recipe["meal_type"] == request["preferred_meal_type"],
    }
    return result, None, missing_groups


def _format_unlock_suggestions(unlock_map: dict[tuple[str, str], set[str]]) -> list[dict[str, Any]]:
    rows = sorted(unlock_map.items(), key=lambda item: (-len(item[1]), item[0][1]))[:5]
    suggestions: list[dict[str, Any]] = []
    for (item_type, name), recipe_names in rows:
        names = sorted(recipe_names)
        preview = ", ".join(names[:3])
        suffix = f" 외 {len(names) - 3}개" if len(names) > 3 else ""
        suggestions.append(
            {
                "type": item_type,
                "name": name,
                "unlocks": len(names),
                "recipe_names": names,
                "message": f"{name} 추가 → {preview}{suffix} 가능",
            }
        )
    return suggestions


def recommend(
    inventory: list[dict[str, Any]],
    seasonings: list[dict[str, Any]],
    recipes: list[dict[str, Any]],
    meal_history: list[dict[str, Any]],
    request: dict[str, Any],
) -> dict[str, Any]:
    now = now_kst()
    enriched = enrich_inventory_priority(inventory, now.date())
    excluded_ids = set(request.get("excluded_ingredient_ids", []))
    usable = [
        item
        for item in enriched
        if item["recommendation_eligible"] and item["ingredient_id"] not in excluded_ids
    ]
    if not usable:
        return {
            "status": "empty_inventory",
            "message": "추천에 사용할 수 있는 냉장고 식재료가 없습니다.",
            "suggestions": [
                "식재료를 추가하거나 상태 확인이 필요한 재료를 점검해주세요.",
                "데모 식재료를 불러와 기능을 확인할 수 있습니다.",
            ],
            "preferred_exact_results": [],
            "preferred_other_type_results": [],
            "preferred_exact_one_more_results": [],
            "preferred_other_type_one_more_results": [],
            "alternative_exact_results": [],
            "alternative_other_type_results": [],
            "alternative_exact_one_more_results": [],
            "alternative_other_type_one_more_results": [],
            "preferred_direct_results": [],
            "preferred_one_more_results": [],
            "alternative_results": [],
            "alternative_one_more_results": [],
            "direct_results": [],
            "one_more_results": [],
            "inventory_priority": enriched,
        }

    inventory_by_ingredient: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in usable:
        inventory_by_ingredient[item["ingredient_id"]].append(item)
    for lots in inventory_by_ingredient.values():
        lots.sort(key=lambda x: (-x["ranking_priority_score"], x["purchase_date"], x["id"]))

    top_priority_pairs = sorted(
        (
            (ingredient_id, max(lot["ranking_priority_score"] for lot in lots))
            for ingredient_id, lots in inventory_by_ingredient.items()
        ),
        key=lambda x: x[1],
        reverse=True,
    )[:3]
    top_priority_ids = {ingredient_id for ingredient_id, _ in top_priority_pairs}
    top_priority_denominator = sum(score for _, score in top_priority_pairs) or 1.0

    owned_seasonings = _owned_seasoning_ids(seasonings, request.get("temporary_owned_seasoning_ids"))
    seasoning_names = {item["id"]: item["name"] for item in seasonings}
    preferred_cuisine = request["preferred_cuisine"]
    preferred_meal_type = request.get("preferred_meal_type", "상관없음")
    catalog_counts = Counter(recipe["cuisine"] for recipe in recipes)
    catalog_meal_type_counts = Counter(recipe["meal_type"] for recipe in recipes)
    rejection_counts: Counter[str] = Counter()
    preferred_rejection_counts: Counter[str] = Counter()
    unlock_map: dict[tuple[str, str], set[str]] = defaultdict(set)
    direct: list[dict[str, Any]] = []
    one_more: list[dict[str, Any]] = []

    for recipe in recipes:
        is_preferred = preferred_cuisine == "상관없음" or recipe["cuisine"] == preferred_cuisine
        result, rejected_reason, missing_groups = _evaluate_recipe(
            recipe,
            inventory_by_ingredient,
            owned_seasonings,
            top_priority_ids,
            top_priority_denominator,
            meal_history,
            request,
            seasoning_names,
            now,
        )
        if rejected_reason:
            rejection_counts[rejected_reason] += 1
            if is_preferred:
                preferred_rejection_counts[rejected_reason] += 1
            continue
        if result is None:
            continue
        if result["missing_to_make"]:
            one_more.append(result)
            if is_preferred and result["missing_units"] == 1:
                missing = result["missing_to_make"][0]
                unlock_map[(missing["type"], missing["name"])].add(result["name"])
        else:
            direct.append(result)

    direct.sort(key=lambda x: (-x["score"], x["cook_time"], x["name"]))
    one_more.sort(key=lambda x: (-x["score"], x["cook_time"], x["name"]))

    def cuisine_matches(item: dict[str, Any]) -> bool:
        return preferred_cuisine == "상관없음" or item["cuisine"] == preferred_cuisine

    def type_matches(item: dict[str, Any]) -> bool:
        return preferred_meal_type == "상관없음" or item["meal_type"] == preferred_meal_type

    preferred_exact = [x for x in direct if cuisine_matches(x) and type_matches(x)]
    preferred_other_type = [x for x in direct if cuisine_matches(x) and not type_matches(x)]
    preferred_exact_one = [x for x in one_more if cuisine_matches(x) and type_matches(x)]
    preferred_other_type_one = [x for x in one_more if cuisine_matches(x) and not type_matches(x)]

    if preferred_cuisine == "상관없음":
        alternative_exact: list[dict[str, Any]] = []
        alternative_other_type: list[dict[str, Any]] = []
        alternative_exact_one: list[dict[str, Any]] = []
        alternative_other_type_one: list[dict[str, Any]] = []
    else:
        alternative_exact = [x for x in direct if x["cuisine"] != preferred_cuisine and type_matches(x)]
        alternative_other_type = [x for x in direct if x["cuisine"] != preferred_cuisine and not type_matches(x)]
        alternative_exact_one = [x for x in one_more if x["cuisine"] != preferred_cuisine and type_matches(x)]
        alternative_other_type_one = [x for x in one_more if x["cuisine"] != preferred_cuisine and not type_matches(x)]

    preferred_direct = preferred_exact + preferred_other_type
    preferred_one_more = preferred_exact_one + preferred_other_type_one
    alternatives = alternative_exact + alternative_other_type
    alternative_one_more = alternative_exact_one + alternative_other_type_one

    messages: list[str] = []
    condition_label = (
        f"{preferred_cuisine}·{preferred_meal_type}"
        if preferred_cuisine != "상관없음" and preferred_meal_type != "상관없음"
        else preferred_cuisine if preferred_cuisine != "상관없음"
        else preferred_meal_type if preferred_meal_type != "상관없음"
        else "선택 조건"
    )
    if preferred_exact:
        messages.append(f"{condition_label}에 완전히 맞는 바로 조리 메뉴 {len(preferred_exact)}개를 찾았습니다.")
    else:
        messages.append(f"현재 재고와 조리 조건을 모두 만족하는 {condition_label} 메뉴는 없습니다.")
    if preferred_other_type and preferred_meal_type != "상관없음":
        messages.append(f"같은 음식 계열이지만 식사 형태가 다른 메뉴 {len(preferred_other_type)}개를 별도 표시합니다.")
    if preferred_exact_one:
        messages.append(f"항목 하나만 추가하면 원하는 조건으로 만들 수 있는 메뉴가 {len(preferred_exact_one)}개 있습니다.")
    if alternatives and request.get("cuisine_preference_strength") != "strict":
        messages.append(f"다른 음식 계열의 대체 메뉴 {len(alternatives)}개도 분리해 제시합니다.")
    if request.get("cuisine_preference_strength") == "strict" and not preferred_direct and not preferred_one_more:
        messages.append("'해당 계열만 추천' 조건 때문에 다른 음식 계열은 표시하지 않았습니다.")

    unlock_suggestions = _format_unlock_suggestions(unlock_map)
    for suggestion in unlock_suggestions[:2]:
        messages.append(suggestion["message"])

    all_grouped = [
        preferred_exact,
        preferred_other_type,
        preferred_exact_one,
        preferred_other_type_one,
        alternative_exact,
        alternative_other_type,
        alternative_exact_one,
        alternative_other_type_one,
    ]
    any_results = any(all_grouped)

    request_summary = {
        "preferred_cuisine": preferred_cuisine,
        "cuisine_preference_strength": CUISINE_PREFERENCE_LABELS[request["cuisine_preference_strength"]],
        "preferred_meal_type": preferred_meal_type,
        "previous_meal_cuisine": request.get("previous_meal_cuisine", "입력하지 않음"),
        "previous_meal_type": request.get("previous_meal_type", "입력하지 않음"),
        "previous_meal_avoidance": PREVIOUS_MEAL_AVOIDANCE_LABELS[request["previous_meal_avoidance"]],
        "max_cooking_minutes": request["max_cooking_minutes"],
        "appliances": request["appliances"],
        "allow_substitutions": request.get("allow_substitutions", True),
    }
    diagnostics = {
        "catalog_by_cuisine": dict(catalog_counts),
        "catalog_by_meal_type": dict(catalog_meal_type_counts),
        "rejection_counts": dict(rejection_counts),
        "preferred_rejection_counts": dict(preferred_rejection_counts),
        "unlock_suggestions": unlock_suggestions,
        "counts": {
            "preferred_exact_direct": len(preferred_exact),
            "preferred_other_type_direct": len(preferred_other_type),
            "preferred_exact_one_more": len(preferred_exact_one),
            "preferred_other_type_one_more": len(preferred_other_type_one),
            "alternative_exact_direct": len(alternative_exact),
            "alternative_other_type_direct": len(alternative_other_type),
        },
    }

    if not any_results:
        return {
            "status": "no_candidates",
            "message": "현재 조건을 만족하는 메뉴가 없습니다.",
            "suggestions": [
                "조리 가능 시간을 늘려보세요.",
                "사용 가능한 조리기구를 추가해보세요.",
                "음식 계열 적용 강도를 완화해보세요.",
                "직전 식사 회피 조건을 '가능하면 피하기'로 변경해보세요.",
            ],
            "analysis_messages": messages,
            "request_summary": request_summary,
            "diagnostics": diagnostics,
            "preferred_exact_results": [],
            "preferred_other_type_results": [],
            "preferred_exact_one_more_results": [],
            "preferred_other_type_one_more_results": [],
            "alternative_exact_results": [],
            "alternative_other_type_results": [],
            "alternative_exact_one_more_results": [],
            "alternative_other_type_one_more_results": [],
            "preferred_direct_results": [],
            "preferred_one_more_results": [],
            "alternative_results": [],
            "alternative_one_more_results": [],
            "direct_results": [],
            "one_more_results": [],
            "inventory_priority": enriched,
        }

    preferred_exact_out = preferred_exact[:5]
    preferred_other_type_out = preferred_other_type[:4]
    preferred_exact_one_out = preferred_exact_one[:5]
    preferred_other_type_one_out = preferred_other_type_one[:3]
    alternative_exact_out = alternative_exact[:4]
    alternative_other_type_out = alternative_other_type[:3]
    alternative_exact_one_out = alternative_exact_one[:3]
    alternative_other_type_one_out = alternative_other_type_one[:2]

    preferred_direct_out = preferred_exact_out + preferred_other_type_out
    preferred_one_more_out = preferred_exact_one_out + preferred_other_type_one_out
    alternatives_out = alternative_exact_out + alternative_other_type_out
    alternative_one_more_out = alternative_exact_one_out + alternative_other_type_one_out
    combined_direct = preferred_direct_out + [
        x for x in alternatives_out if x["recipe_id"] not in {y["recipe_id"] for y in preferred_direct_out}
    ]
    combined_one_more = preferred_one_more_out + [
        x for x in alternative_one_more_out if x["recipe_id"] not in {y["recipe_id"] for y in preferred_one_more_out}
    ]

    return {
        "status": "ok",
        "message": "저장된 냉장고·양념장·현재 설문·최근 식사 이력을 함께 반영했습니다.",
        "request_summary": request_summary,
        "analysis_messages": messages,
        "diagnostics": diagnostics,
        "scoring_policy": {
            "mode": request["recommendation_mode"],
            "mode_label": MODE_LABELS[request["recommendation_mode"]],
            "weights": MODE_WEIGHTS[request["recommendation_mode"]],
            "note": "식품 안전 확률이 아니라 서비스 정책에 따라 후보의 상대 순위를 정하는 점수입니다.",
        },
        "preferred_exact_results": preferred_exact_out,
        "preferred_other_type_results": preferred_other_type_out,
        "preferred_exact_one_more_results": preferred_exact_one_out,
        "preferred_other_type_one_more_results": preferred_other_type_one_out,
        "alternative_exact_results": alternative_exact_out,
        "alternative_other_type_results": alternative_other_type_out,
        "alternative_exact_one_more_results": alternative_exact_one_out,
        "alternative_other_type_one_more_results": alternative_other_type_one_out,
        "preferred_direct_results": preferred_direct_out,
        "preferred_one_more_results": preferred_one_more_out,
        "alternative_results": alternatives_out,
        "alternative_one_more_results": alternative_one_more_out,
        "direct_results": combined_direct,
        "one_more_results": combined_one_more,
        "inventory_priority": enriched,
    }
