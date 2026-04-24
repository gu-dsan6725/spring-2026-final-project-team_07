import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Personal Nutritionist", page_icon="🥗", layout="wide")

st.markdown("""
<style>
/* ── Global typography ─────────────────────────────────────────── */
html, body, [class*="css"] { font-family: "Inter", "Segoe UI", sans-serif; }

/* ── Header bar ────────────────────────────────────────────────── */
.app-header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 18px 0 10px 0;
    border-bottom: 2px solid #C8E6C9;
    margin-bottom: 20px;
}
.app-header .icon { font-size: 2rem; line-height: 1; }
.app-header h1 {
    margin: 0;
    font-size: 1.7rem;
    font-weight: 700;
    color: #1B5E20;
    letter-spacing: -0.3px;
}
.app-header .subtitle {
    font-size: 0.82rem;
    color: #558B2F;
    margin: 0;
    font-weight: 400;
}

/* ── Sidebar ───────────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: #EFF3EE;
    border-right: 1px solid #C8E6C9;
}
section[data-testid="stSidebar"] .stMetric { background: transparent; }

/* ── Recipe cards in sidebar ───────────────────────────────────── */
section[data-testid="stSidebar"] div[data-testid="stVerticalBlockBorderWrapper"] {
    background: #FFFFFF;
    border: 1px solid #C8E6C9 !important;
    border-radius: 10px !important;
    padding: 6px 8px !important;
    margin-bottom: 6px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}

/* ── Main panel cards / expanders ─────────────────────────────── */
div[data-testid="stExpander"] {
    border: 1px solid #C8E6C9;
    border-radius: 10px;
    overflow: hidden;
    margin-bottom: 8px;
    background: #FFFFFF;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
div[data-testid="stExpander"] summary {
    background: #F1F8F0;
    font-weight: 600;
    padding: 10px 14px;
}

/* ── Chat bubbles ──────────────────────────────────────────────── */
div[data-testid="stChatMessage"] {
    border-radius: 12px;
    padding: 4px 8px;
    margin-bottom: 4px;
}

/* ── Metric labels ─────────────────────────────────────────────── */
div[data-testid="stMetric"] label { font-size: 0.72rem !important; color: #558B2F; }
div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
    font-size: 1.05rem !important;
    font-weight: 700;
    color: #1B5E20;
}

/* ── Buttons ───────────────────────────────────────────────────── */
div.stButton > button[kind="primary"] {
    background: #2E7D32;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    letter-spacing: 0.2px;
}
div.stButton > button[kind="primary"]:hover { background: #1B5E20; }
div.stButton > button:not([kind="primary"]) {
    border-radius: 8px;
    border: 1px solid #A5D6A7;
    color: #2E7D32;
    background: transparent;
}
div.stButton > button:not([kind="primary"]):hover {
    background: #E8F5E9;
    border-color: #2E7D32;
}

/* ── Download button ───────────────────────────────────────────── */
div.stDownloadButton > button {
    border-radius: 8px;
    border: 1px solid #A5D6A7;
    color: #2E7D32;
    background: transparent;
    font-weight: 500;
}
div.stDownloadButton > button:hover { background: #E8F5E9; }

/* ── Divider ───────────────────────────────────────────────────── */
hr { border-color: #C8E6C9; }

/* ── Tab strip ─────────────────────────────────────────────────── */
div[data-testid="stTabs"] button[role="tab"] {
    font-weight: 500;
    color: #558B2F;
}
div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    color: #1B5E20;
    border-bottom-color: #2E7D32 !important;
}

/* ── Text inputs / selects ─────────────────────────────────────── */
div[data-testid="stTextInput"] input,
div[data-testid="stSelectbox"] div[data-baseweb="select"] {
    border-radius: 8px !important;
}
</style>
""", unsafe_allow_html=True)

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="app-header">
  <span class="icon">🥗</span>
  <div>
    <h1>Personal Nutritionist</h1>
    <p class="subtitle">AI-powered meal planning tailored to you</p>
  </div>
</div>
""", unsafe_allow_html=True)

col_user, _ = st.columns([1, 3])
with col_user:
    user_id = st.text_input("User ID", placeholder="e.g. andrew", label_visibility="visible")

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

    from personal_nutritionist.core.dependencies import get_recipe_df
    df = get_recipe_df(user_id=user_id)

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

    _SB_CAT_LABELS = {
        "main_dish": "Main Dish", "breakfast": "Breakfast", "side_dish": "Side Dish",
        "snack": "Snack", "dessert": "Dessert", "drink": "Drink",
    }
    for _, row in page_df.iterrows():
        with st.container(border=True):
            st.markdown(f"**{row['title']}**")
            st.caption(_SB_CAT_LABELS.get(row['category'], row['category']))
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
        user_id=user_id,
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
    tab_chat, tab_profile, tab_cookbook = st.tabs(["Chat", "Profile", "Cookbook"])

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

            # If the agent built a meal plan, capture it for the right panel.
            import personal_nutritionist.agents.orchestrator.tools as _orch_tools
            if _orch_tools.last_plan_result and "plan" in _orch_tools.last_plan_result:
                raw = _orch_tools.last_plan_result["plan"]
                st.session_state.week_plan = raw if isinstance(raw, list) else [raw]
                _orch_tools.last_plan_result = None
                st.rerun()

    with tab_profile:
        if st.button("Refresh Profile"):
            st.session_state.pop("cached_profile", None)
            st.session_state.pop("cached_memories", None)

        if "cached_profile" not in st.session_state:
            from personal_nutritionist.agents.planning.tools import (
                get_user_profile,
                estimate_calorie_target,
                estimate_protein_target,
            )
            from personal_nutritionist.core.memory import get_memory
            with st.spinner("Loading profile..."):
                st.session_state.cached_profile = get_user_profile(user_id)
                st.session_state.cached_memories = get_memory(user_id)

        profile = st.session_state.cached_profile
        memories = st.session_state.cached_memories

        _ENUM_LABELS = {
            "fat_loss": "Fat Loss",
            "muscle_gain": "Muscle Gain",
            "maintenance": "Maintenance",
            "sedentary": "Sedentary",
            "light": "Light",
            "moderate": "Moderate",
            "active": "Active",
            "very_active": "Very Active",
            "male": "Male",
            "female": "Female",
        }

        def _fmt(value):
            if value is None:
                return "Not set"
            if isinstance(value, list):
                return ", ".join(value) if value else "None"
            if isinstance(value, str):
                return _ENUM_LABELS.get(value, value.replace("_", " ").title())
            if isinstance(value, float):
                return f"{value:g}"
            return str(value)

        def _row(col_a, col_b, label, value):
            col_a.markdown(f"**{label}**")
            col_b.markdown(_fmt(value))

        st.subheader("Personal Info")
        a, b = st.columns([1, 2])
        _row(a, b, "Goal", profile.get("goal"))
        _row(a, b, "Sex", profile.get("sex"))
        _row(a, b, "Age", profile.get("age"))
        _row(a, b, "Weight", f"{profile['weight_lbs']:g} lbs" if profile.get("weight_lbs") else "Not set")
        _row(a, b, "Height", f"{profile['height_in']:g} in" if profile.get("height_in") else "Not set")
        _row(a, b, "Activity Level", profile.get("activity_level"))

        st.divider()
        st.subheader("Daily Targets")
        _has_targets = all(profile.get(f) for f in ("goal", "weight_lbs", "height_in", "age", "sex"))
        if _has_targets:
            from personal_nutritionist.agents.planning.tools import (
                estimate_calorie_target,
                estimate_protein_target,
            )
            _cal = estimate_calorie_target(profile)
            _pro = estimate_protein_target(profile)
            c1, c2 = st.columns(2)
            c1.metric("Calories / day", f"{_cal:,.0f} kcal")
            c2.metric("Protein / day", f"{_pro:,.0f} g")
        else:
            st.caption("Complete your profile to see calorie and protein targets.")

        st.divider()
        st.subheader("Meal Constraints")
        a, b = st.columns([1, 2])
        _row(a, b, "Meals per Day", profile.get("meals_per_day"))
        _row(a, b, "Max Cost / Serving", f"${profile['max_cost_per_serving']:g}" if profile.get("max_cost_per_serving") else "Not set")
        _row(a, b, "Max Cook Time", f"{profile['max_total_time']} min" if profile.get("max_total_time") else "Not set")
        _row(a, b, "Max Ingredients", profile.get("max_ingredient_count"))

        st.divider()
        st.subheader("Dietary Preferences")
        a, b = st.columns([1, 2])
        _row(a, b, "Allergies", profile.get("allergies"))
        _row(a, b, "Disliked Ingredients", profile.get("disliked_ingredients"))
        _row(a, b, "Preferred Categories", profile.get("preferred_categories"))

        with st.expander("Raw Memories", expanded=False):
            if not memories:
                st.info("No memories stored yet. Chat with the bot to build your profile.")
            else:
                for m in memories:
                    st.markdown(f"- {m.get('memory', '')}")

    with tab_cookbook:
        from personal_nutritionist.core.database import (
            get_custom_recipes, get_excluded,
            remove_from_cookbook, restore_to_cookbook, remove_custom_recipe,
            remove_all_from_cookbook, restore_all_to_cookbook,
        )
        from personal_nutritionist.core.dependencies import get_recipe_df as _get_df

        st.subheader("Your Cookbook")
        st.caption("All recipes available to you. Remove ones you don't want; restore them any time.")

        bulk_col1, bulk_col2 = st.columns(2)
        with bulk_col1:
            if st.button("Remove all recipes", use_container_width=True):
                base_df = _get_df()
                all_base_titles = base_df["title"].tolist()
                remove_all_from_cookbook(user_id, all_base_titles)
                st.rerun()
        with bulk_col2:
            if st.button("Restore all default recipes", use_container_width=True):
                restore_all_to_cookbook(user_id)
                st.rerun()

        cb_search = st.text_input("Search cookbook", placeholder="e.g. pasta", key="cb_search")

        base_df = _get_df()
        excluded = get_excluded(user_id)
        custom = {r["title"]: r for r in get_custom_recipes(user_id)}

        all_titles = set(base_df["title"].tolist()) | set(custom.keys())
        active_titles = all_titles - excluded
        removed_titles = all_titles & excluded

        def _matches(title: str) -> bool:
            return not cb_search or cb_search.lower() in title.lower()

        # ── Active recipes ──
        active_filtered = sorted(t for t in active_titles if _matches(t))
        st.markdown(f"**{len(active_filtered)} recipes** — select one to view or edit")

        from personal_nutritionist.core.database import edit_custom_recipe as _edit_recipe

        _CATEGORY_OPTIONS = [
            "main_dish", "breakfast", "side_dish", "snack", "dessert", "drink",
        ]
        _CATEGORY_LABELS = {
            "main_dish": "Main Dish",
            "breakfast": "Breakfast",
            "side_dish": "Side Dish",
            "snack": "Snack",
            "dessert": "Dessert",
            "drink": "Drink",
        }

        for title in active_filtered:
            is_custom = title in custom
            tag = " [custom]" if is_custom else ""

            if is_custom:
                r = custom[title]
            else:
                rows = base_df[base_df["title"] == title]
                r = rows.iloc[0].to_dict() if not rows.empty else {}

            cal = r.get("calories", 0) or 0
            prot = r.get("protein", 0) or 0
            cost = r.get("cost_per_serving", 0) or 0
            label = f"{title}{tag} — {cal:.0f} kcal | {prot:.1f}g protein | ${cost:.2f}/serving"

            with st.expander(label):
                if is_custom:
                    with st.form(key=f"edit_{title}"):
                        new_title = st.text_input("Title", value=r.get("title", title))
                        c1, c2 = st.columns(2)
                        _cur_cat = str(r.get("category", "main_dish"))
                        _cat_idx = _CATEGORY_OPTIONS.index(_cur_cat) if _cur_cat in _CATEGORY_OPTIONS else 0
                        new_cat = c1.selectbox(
                            "Category",
                            options=_CATEGORY_OPTIONS,
                            index=_cat_idx,
                            format_func=lambda x: _CATEGORY_LABELS[x],
                        )
                        new_servings = c2.number_input("Servings",         value=float(r.get("servings", 4)),   min_value=0.0)
                        new_cal      = c1.number_input("Calories",         value=float(r.get("calories", 0)),   min_value=0.0)
                        new_prot     = c2.number_input("Protein (g)",      value=float(r.get("protein", 0)),    min_value=0.0)
                        new_fat      = c1.number_input("Fat (g)",          value=float(r.get("fat", 0)),        min_value=0.0)
                        new_carbs    = c2.number_input("Carbs (g)",        value=float(r.get("carbs", 0)),      min_value=0.0)
                        new_cost     = c1.number_input("Cost/serving ($)", value=float(r.get("cost_per_serving", 0)), min_value=0.0)
                        new_prep     = c1.number_input("Prep time (min)",  value=int(r.get("prep_time", 0)),    min_value=0, step=1)
                        new_cook     = c2.number_input("Cook time (min)",  value=int(r.get("cook_time", 0)),    min_value=0, step=1)
                        new_ings     = st.text_area("Ingredients (one per line)",
                                                    value="\n".join(r.get("ingredients", [])), height=120)
                        new_steps    = st.text_area("Steps (one per line)",
                                                    value="\n".join(r.get("steps", [])), height=120)

                        save_col, del_col = st.columns([3, 1])
                        saved   = save_col.form_submit_button("Save changes", type="primary", use_container_width=True)
                        deleted = del_col.form_submit_button("Delete recipe", use_container_width=True)

                    if saved:
                        updates = {
                            "title": new_title,
                            "category": new_cat,
                            "servings": new_servings,
                            "calories": new_cal,
                            "protein": new_prot,
                            "fat": new_fat,
                            "carbs": new_carbs,
                            "cost_per_serving": new_cost,
                            "total_cost": new_cost * new_servings,
                            "prep_time": new_prep,
                            "cook_time": new_cook,
                            "total_time": new_prep + new_cook,
                            "ingredients": [l for l in new_ings.splitlines() if l.strip()],
                            "steps": [l for l in new_steps.splitlines() if l.strip()],
                            "ingredient_count": len([l for l in new_ings.splitlines() if l.strip()]),
                            "num_steps": len([l for l in new_steps.splitlines() if l.strip()]),
                        }
                        _edit_recipe(user_id, title, updates)
                        st.rerun()

                    if deleted:
                        remove_custom_recipe(user_id, title)
                        st.rerun()

                else:
                    # Base recipe — read-only display
                    c1, c2 = st.columns(2)
                    _cat_raw = r.get("category", "")
                    c1.markdown(f"**Category:** {_CATEGORY_LABELS.get(_cat_raw, _cat_raw) or '—'}")
                    c2.markdown(f"**Servings:** {r.get('servings', '—')}")
                    c1.markdown(f"**Calories:** {r.get('calories', 0):.0f}")
                    c2.markdown(f"**Protein:** {r.get('protein', 0):.1f}g")
                    c1.markdown(f"**Fat:** {r.get('fat', 0):.1f}g")
                    c2.markdown(f"**Carbs:** {r.get('carbs', 0):.1f}g")
                    c1.markdown(f"**Cost/serving:** ${r.get('cost_per_serving', 0):.2f}")
                    c2.markdown(f"**Total time:** {r.get('total_time', 0)} min")
                    c1.markdown(f"**Rating:** {r.get('rating', 0):.1f} ({r.get('rating_count', 0)} ratings)")
                    ings = r.get("ingredients", [])
                    if ings:
                        st.markdown("**Ingredients:** " + " · ".join(ings[:8]) + (" ..." if len(ings) > 8 else ""))
                    if st.button("Remove from cookbook", key=f"rm_{title}", use_container_width=True):
                        remove_from_cookbook(user_id, title)
                        st.rerun()

        # ── Removed recipes ──
        if removed_titles:
            removed_filtered = sorted(t for t in removed_titles if _matches(t))
            if removed_filtered:
                with st.expander(f"Removed recipes ({len(removed_filtered)})"):
                    for title in removed_filtered:
                        col_name, col_btn = st.columns([6, 1])
                        col_name.markdown(f"~~{title}~~")
                        with col_btn:
                            if st.button("Restore", key=f"restore_{title}", use_container_width=True):
                                restore_to_cookbook(user_id, title)
                                st.rerun()


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
                try:
                    st.session_state.week_plan = _generate_plan(user_id, n_days=int(n_days))
                    st.rerun()
                except ValueError as e:
                    st.error(f"Could not build plan: {e}")

    if "week_plan" not in st.session_state or not st.session_state.week_plan:
        st.info("Generate a plan, or ask the chatbot to build one.")
    else:
        from personal_nutritionist.agents.planning.tools import search_meals_tool
        from personal_nutritionist.agents.orchestrator.tools import generate_shopping_list
        import csv, io

        plan: list[dict] = st.session_state.week_plan

        shopping = generate_shopping_list({"plan": plan})
        if "items" in shopping:
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(["Ingredient", "Quantity"])
            for item in shopping["items"]:
                writer.writerow([item["ingredient"], item["quantity"] or ""])
            st.download_button(
                "Download Shopping List (CSV)",
                data=buf.getvalue(),
                file_name="shopping_list.csv",
                mime="text/csv",
                use_container_width=True,
            )

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
