import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Personal Nutritionist", page_icon="🥗", layout="wide")

# ── Header ─────────────────────────────────────────────────────────────────────
col_title, col_user = st.columns([4, 1])
with col_title:
    st.title("Personal Nutritionist")
with col_user:
    user_id = st.text_input("User ID", placeholder="e.g. andrew", label_visibility="collapsed")
    st.caption("User ID")

if not user_id:
    st.info("Enter a User ID above to get started.")
    st.stop()

# ── Agent (one per user_id) ────────────────────────────────────────────────────
if "agent" not in st.session_state or st.session_state.get("agent_user_id") != user_id:
    from personal_nutritionist.agents.orchestrator.agent import create_orchestrator
    st.session_state.agent = create_orchestrator(user_id=user_id)
    st.session_state.agent_user_id = user_id
    st.session_state.messages = []

# ── Sidebar — Recipe Browser ───────────────────────────────────────────────────
with st.sidebar:
    st.subheader("Recipe Browser")

    if "recipe_df" not in st.session_state:
        from personal_nutritionist.core.dependencies import get_recipe_df
        st.session_state.recipe_df = get_recipe_df()

    df = st.session_state.recipe_df

    search = st.text_input("Search", placeholder="e.g. chicken")
    categories = sorted(df["category"].dropna().unique().tolist())
    selected_cat = st.selectbox("Category", ["All"] + categories)
    sort_by = st.selectbox("Sort by", ["rating", "calories", "protein", "cost_per_serving", "total_time"])

    filtered = df.copy()
    if search:
        filtered = filtered[filtered["title"].str.contains(search, case=False, na=False)]
    if selected_cat != "All":
        filtered = filtered[filtered["category"] == selected_cat]
    filtered = filtered.sort_values(sort_by, ascending=(sort_by not in {"rating", "protein"}))

    st.caption(f"{len(filtered)} recipes")

    PAGE_SIZE = 10
    total_pages = max(1, (len(filtered) - 1) // PAGE_SIZE + 1)
    page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1)
    page_df = filtered.iloc[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]

    for _, row in page_df.iterrows():
        with st.container(border=True):
            st.markdown(f"**{row['title']}**")
            st.caption(f"{row['category']}")
            c1, c2, c3 = st.columns(3)
            c1.metric("kcal", f"{row['calories']:.0f}")
            c2.metric("protein", f"{row['protein']:.0f}g")
            c3.metric("cost", f"${row['cost_per_serving']:.2f}")
            c1.caption(f"{row['total_time']} min")
            c2.caption(f"★ {row['rating']:.1f}")
            c3.caption(f"{row['servings']:.0f} serv")


# ── Helpers ────────────────────────────────────────────────────────────────────
SLOTS = ["breakfast", "lunch", "lunch_side", "dinner", "dinner_side", "snack"]
SLOT_LABELS = {
    "breakfast": "Breakfast",
    "lunch": "Lunch",
    "lunch_side": "Lunch Side",
    "dinner": "Dinner",
    "dinner_side": "Dinner Side",
    "snack": "Snack",
}

def _recipe_line(recipe: dict) -> str:
    return (
        f"{recipe['title']} — "
        f"{recipe['calories']:.0f} kcal | "
        f"{recipe['protein']:.1f}g protein | "
        f"${recipe['cost_per_serving']:.2f}/serving"
    )

def _generate_plan(user_id: str, n_days: int = 7) -> list[dict]:
    from personal_nutritionist.agents.planning.tools import (
        build_week_plan_tool,
        get_user_profile,
        estimate_calorie_target,
        estimate_protein_target,
    )
    profile = get_user_profile(user_id)
    calorie_target = estimate_calorie_target(profile)
    protein_target = estimate_protein_target(profile)
    filters = {
        "max_cost_per_serving": profile.get("max_cost_per_serving"),
        "max_total_time": profile.get("max_total_time"),
        "exclude_ingredients": profile.get("allergies", []) + profile.get("disliked_ingredients", []),
    }
    return build_week_plan_tool(
        filters_dict=filters,
        n_days=n_days,
        include_snack=profile.get("meals_per_day", 3) > 3,
        include_side=profile.get("meals_per_day", 3) > 4,
        calorie_target=calorie_target,
        protein_target=protein_target,
        goal=profile.get("goal", "maintenance"),
    )

def _recalc_totals(day: dict) -> dict:
    cal = sum(r["calories"] for r in [day.get(s) for s in SLOTS] if r)
    prot = sum(r["protein"] for r in [day.get(s) for s in SLOTS] if r)
    cost = sum(r["cost_per_serving"] for r in [day.get(s) for s in SLOTS] if r)
    return {"calories": cal, "protein": prot, "cost": cost}


# ── Main layout: left = tabs, right = meal plan ────────────────────────────────
left, right = st.columns([1, 1], gap="large")

# ── LEFT — Chat / Profile tabs ────────────────────────────────────────────────
with left:
    tab_chat, tab_profile = st.tabs(["Chat", "Profile"])

    with tab_chat:
        if st.button("New conversation"):
            from personal_nutritionist.agents.orchestrator.agent import create_orchestrator
            st.session_state.agent = create_orchestrator(user_id=user_id)
            st.session_state.messages = []

        for msg in st.session_state.messages:
            st.chat_message(msg["role"]).write(msg["content"])

        if prompt := st.chat_input("Ask me about your meals or profile..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            st.chat_message("user").write(prompt)
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    response = str(st.session_state.agent(prompt))
                st.write(response)
            st.session_state.messages.append({"role": "assistant", "content": response})

    with tab_profile:
        if st.button("Refresh profile"):
            st.session_state.pop("cached_profile", None)
            st.session_state.pop("cached_memories", None)

        if "cached_profile" not in st.session_state:
            from personal_nutritionist.agents.planning.tools import get_user_profile
            from personal_nutritionist.core.memory import get_memory
            with st.spinner("Loading profile..."):
                st.session_state.cached_profile = get_user_profile(user_id)
                st.session_state.cached_memories = get_memory(user_id)

        profile = st.session_state.cached_profile
        memories = st.session_state.cached_memories

        LABELS = {
            "goal": "Goal",
            "weight_lbs": "Weight (lbs)",
            "height_in": "Height (in)",
            "age": "Age",
            "sex": "Sex",
            "activity_level": "Activity Level",
            "target_calories": "Target Calories",
            "target_protein": "Target Protein (g)",
            "max_cost_per_serving": "Max Cost / Serving ($)",
            "max_total_time": "Max Cook Time (min)",
            "max_ingredient_count": "Max Ingredients",
            "meals_per_day": "Meals / Day",
            "preferred_categories": "Preferred Categories",
            "disliked_ingredients": "Disliked Ingredients",
            "allergies": "Allergies",
        }

        st.subheader("Resolved Profile")
        for field, label in LABELS.items():
            value = profile.get(field)
            if value is None:
                continue
            if isinstance(value, list):
                display = ", ".join(value) if value else "—"
            elif isinstance(value, float):
                display = f"{value:g}"
            else:
                display = str(value)
            st.markdown(f"**{label}:** {display}")

        st.subheader("Stored Memories")
        if not memories:
            st.info("No memories stored yet. Chat with the bot to build your profile.")
        else:
            for m in memories:
                st.markdown(f"- {m.get('memory', '')}")


# ── RIGHT — Persistent Meal Plan ───────────────────────────────────────────────
with right:
    st.subheader("Meal Plan")

    gen_col, days_col = st.columns([2, 1])
    with days_col:
        n_days = st.number_input("Days", min_value=1, max_value=14, value=7, step=1, key="n_days")
    with gen_col:
        st.write("")
        if st.button("Generate Plan", type="primary", use_container_width=True):
            with st.spinner("Building meal plan..."):
                st.session_state.week_plan = _generate_plan(user_id, n_days=int(n_days))
            st.rerun()

    if "week_plan" not in st.session_state or not st.session_state.week_plan:
        st.info("Generate a plan, or ask the chatbot to build one.")
    else:
        from personal_nutritionist.agents.planning.tools import search_meals_tool

        plan: list[dict] = st.session_state.week_plan

        for i, day in enumerate(plan):
            t = day["totals"]
            header = f"Day {i + 1}  —  {t['calories']:.0f} kcal | {t['protein']:.1f}g protein | ${t['cost']:.2f}"
            with st.expander(header, expanded=(i == 0)):
                for slot in SLOTS:
                    recipe = day.get(slot)
                    if recipe is None:
                        continue

                    swap_key = f"swap_{i}_{slot}"
                    r_col, btn_col = st.columns([5, 1])
                    with r_col:
                        st.markdown(f"**{SLOT_LABELS[slot]}:** {_recipe_line(recipe)}")
                    with btn_col:
                        label = "Cancel" if st.session_state.get(swap_key) else "Swap"
                        if st.button(label, key=f"btn_{i}_{slot}", use_container_width=True):
                            st.session_state[swap_key] = not st.session_state.get(swap_key, False)
                            st.rerun()

                    if st.session_state.get(swap_key):
                        with st.container(border=True):
                            q = st.text_input("Search", placeholder="keyword", key=f"q_{i}_{slot}", label_visibility="collapsed")
                            find_col, _ = st.columns([1, 3])
                            with find_col:
                                if st.button("Find", key=f"find_{i}_{slot}", use_container_width=True):
                                    meal_slot = slot.replace("_side", "") if "side" in slot else slot
                                    results = search_meals_tool(
                                        slot=meal_slot,
                                        filters_dict={"title_contains": q or None, "limit": 8},
                                    )
                                    st.session_state[f"alts_{i}_{slot}"] = results

                            alts = st.session_state.get(f"alts_{i}_{slot}", [])
                            if alts:
                                options = {r["title"]: r for r in alts}
                                chosen = st.radio("Pick replacement", list(options.keys()), key=f"pick_{i}_{slot}", label_visibility="collapsed")
                                if st.button("Apply", key=f"apply_{i}_{slot}", type="primary"):
                                    st.session_state.week_plan[i][slot] = options[chosen]
                                    st.session_state.week_plan[i]["totals"] = _recalc_totals(st.session_state.week_plan[i])
                                    st.session_state[swap_key] = False
                                    st.session_state.pop(f"alts_{i}_{slot}", None)
                                    st.rerun()
