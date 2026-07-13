CONDITION_QUESTIONS = {
    "cooked_food": ["평소와 다른 냄새", "표면의 점액 또는 심한 변색", "보관 상태를 직접 확인해야 함"],
    "fermented": ["제품 특성과 다른 곰팡이", "이물질", "용기 파손 또는 누액"],
    "egg": ["껍데기 파손 또는 누액", "깨뜨렸을 때 평소와 다른 냄새", "직접 확인 필요"],
    "tofu": ["평소와 확연히 다른 냄새", "과도한 점액", "포장 팽창 또는 누액"],
    "raw_meat": ["평소와 확연히 다른 불쾌한 냄새", "과도한 끈적임", "포장 팽창 또는 누액"],
    "seafood": ["평소와 확연히 다른 불쾌한 냄새", "과도한 점액", "포장 팽창 또는 누액"],
    "canned": ["캔 또는 포장 팽창", "누액", "개봉 후 평소와 다른 냄새"],
    "dairy": ["평소와 확연히 다른 냄새", "덩어리짐 또는 분리", "포장 팽창 또는 누액"],
    "cheese_hard": ["원래 제품과 확연히 다른 냄새", "평소에 없던 끈적임", "제품 특성과 무관한 곰팡이"],
    "cheese_soft": ["원래 제품과 확연히 다른 냄새", "평소에 없던 끈적임", "제품 특성과 무관한 곰팡이", "포장 팽창"],
    "cheese_blue": ["원래 숙성 향과 확연히 다른 냄새", "평소에 없던 끈적임", "제품 특성과 다른 색·형태의 곰팡이"],
    "vegetable_leafy": ["광범위한 곰팡이", "심한 무름 또는 진물", "넓은 범위의 변색"],
    "vegetable_root": ["광범위한 곰팡이", "심한 무름 또는 진물", "넓은 범위의 변색"],
    "vegetable_general": ["광범위한 곰팡이", "심한 무름 또는 진물", "넓은 범위의 변색"],
    "fruit_vegetable": ["광범위한 곰팡이", "심한 무름 또는 진물", "넓은 범위의 변색"],
    "bread": ["제품 특성과 무관한 곰팡이", "평소와 다른 냄새", "심한 눅눅함 또는 점액"],
    "dry_food": ["습기 또는 벌레 흔적", "곰팡이", "포장 파손"],
    "processed_food": ["평소와 다른 냄새", "포장 팽창 또는 누액", "과도한 점액"],
    "processed_meat": ["평소와 확연히 다른 냄새", "과도한 점액", "포장 팽창 또는 누액"],
}

MODE_WEIGHTS = {
    "fridge": {"priority": 45, "completeness": 25, "taste": 10, "diversity": 10, "convenience": 10},
    "balanced": {"priority": 35, "completeness": 25, "taste": 20, "diversity": 10, "convenience": 10},
    "taste": {"priority": 25, "completeness": 20, "taste": 35, "diversity": 10, "convenience": 10},
}

MODE_LABELS = {"fridge": "냉장고 소진 우선", "balanced": "균형", "taste": "취향 우선"}
REPEAT_HALF_LIFE = {"low": 1.0, "medium": 2.0, "high": 4.0}

CUISINE_PREFERENCE_LABELS = {
    "soft": "선호함",
    "priority": "가능하면 해당 계열 먼저",
    "strict": "해당 계열만 추천",
}

PREVIOUS_MEAL_AVOIDANCE_LABELS = {
    "none": "상관없음",
    "soft": "가능하면 피하기",
    "exclude_cuisine": "같은 음식 계열 제외",
    "exclude_type": "같은 식사 형태 제외",
    "exclude_either": "같은 계열 또는 식사 형태면 제외",
    "exclude_both": "계열과 식사 형태가 모두 같을 때만 제외",
}
