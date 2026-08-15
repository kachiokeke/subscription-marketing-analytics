"""Show campaign performance and conversion drivers for marketing managers.

The app reads only from prepared DuckDB tables.

Data sources:
- main.mart_campaign_performance
- model_output.model_metrics
- model_output.feature_importance
- model_output.reference_categories
"""

from pathlib import Path

import altair as alt
import duckdb
import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]

LOCAL_WAREHOUSE = PROJECT_ROOT / "warehouse.duckdb"
PORTFOLIO_WAREHOUSE = PROJECT_ROOT / "portfolio.duckdb"

WAREHOUSE = (
    LOCAL_WAREHOUSE
    if LOCAL_WAREHOUSE.exists()
    else PORTFOLIO_WAREHOUSE
)

TARGET_LABELS = {
    "started_trial": "Trial start",
    "made_sale": "Sale",
}

PREDICTOR_LABELS = {
    "gender": "Gender",
    "country": "Country",
    "campaign_label": "Campaign",
    "onboarding_name": "Onboarding experience",
    "attribution_weekday": "Acquisition weekday",
}

# Short labels keep chart categories readable. The full names remain in
# tooltips and supporting tables.
FACTOR_LABELS = {
    "gender": "Gender",
    "country": "Country",
    "campaign_label": "Campaign",
    "onboarding_name": "Onboarding",
    "attribution_weekday": "Weekday",
}

METRIC_OPTIONS = {
    "Total revenue ROAS": {
        "column": "total_revenue_roas",
        "axis_format": ".2f",
        "lower_is_better": False,
    },
    "Initial revenue ROAS": {
        "column": "initial_revenue_roas",
        "axis_format": ".2f",
        "lower_is_better": False,
    },
    "Cost per trial (EUR)": {
        "column": "cost_per_trial",
        "axis_format": ",.2f",
        "lower_is_better": True,
    },
    "Cost per sale (EUR)": {
        "column": "cost_per_sale",
        "axis_format": ",.2f",
        "lower_is_better": True,
    },
    "Trial rate": {
        "column": "trial_rate",
        "axis_format": ".0%",
        "lower_is_better": False,
    },
    "Sale rate": {
        "column": "sale_rate",
        "axis_format": ".0%",
        "lower_is_better": False,
    },
}


st.set_page_config(
    page_title="Subscription Marketing Analytics",
    page_icon="📊",
    layout="wide",
)

st.markdown(
    """
    <style>
        .block-container {
            max-width: 1500px;
            padding-top: 2rem;
            padding-bottom: 4rem;
        }

        div[data-testid="stMetric"] {
            background: #172033;
            border: 1px solid rgba(148, 163, 184, 0.30);
            border-radius: 14px;
            padding: 16px 18px;
        }

        div[data-testid="stMetricLabel"] {
            font-weight: 650;
        }

        div[data-testid="stMetricLabel"] p,
        div[data-testid="stMetricLabel"] label {
            color: #b8c2d1 !important;
        }

        div[data-testid="stMetricValue"],
        div[data-testid="stMetricValue"] > div {
            color: #f8fafc !important;
        }

        .decision-box {
            border-left: 4px solid #4f46e5;
            background: rgba(79, 70, 229, 0.07);
            border-radius: 0 10px 10px 0;
            padding: 14px 18px;
            margin: 10px 0 20px;
        }

        .small-note {
            color: #64748b;
            font-size: 0.92rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False, ttl=60)
def query(sql: str) -> pd.DataFrame:
    """Run one read-only query against the DuckDB warehouse."""

    connection = duckdb.connect(str(WAREHOUSE), read_only=True)

    try:
        return connection.execute(sql).fetchdf()
    finally:
        connection.close()


@st.cache_data(show_spinner=False, ttl=60)
def load_data() -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    """Read the prepared campaign and model-output tables."""

    campaign_data = query(
        """
        select *
        from main.mart_campaign_performance
        order by total_revenue_roas desc
        """
    )

    portfolio_data = query(
        """
        select
            sum(attributed_users) as attributed_users,
            sum(trial_users) as trial_users,
            sum(sale_users) as sale_users,
            sum(total_spend) as total_spend,
            sum(initial_sale_revenue) as initial_sale_revenue,
            sum(total_sale_revenue) as total_sale_revenue,
            cast(sum(trial_users) as double)
                / nullif(sum(attributed_users), 0) as trial_rate,
            cast(sum(sale_users) as double)
                / nullif(sum(attributed_users), 0) as sale_rate,
            sum(total_spend)
                / nullif(sum(trial_users), 0) as cost_per_trial,
            sum(total_spend)
                / nullif(sum(sale_users), 0) as cost_per_sale,
            sum(initial_sale_revenue)
                / nullif(sum(total_spend), 0) as initial_revenue_roas,
            sum(total_sale_revenue)
                / nullif(sum(total_spend), 0) as total_revenue_roas
        from main.mart_campaign_performance
        """
    )

    model_metrics = query(
        """
        select *
        from model_output.model_metrics
        order by target
        """
    )

    feature_importance = query(
        """
        select *
        from model_output.feature_importance
        order by target, absolute_importance desc
        """
    )

    reference_categories = query(
        """
        select *
        from model_output.reference_categories
        order by target, predictor
        """
    )

    return (
        campaign_data,
        portfolio_data,
        model_metrics,
        feature_importance,
        reference_categories,
    )


def format_amount(value: float) -> str:
    """Format a monetary value in EUR."""

    return f"€{value:,.2f}"


def format_percent(value: float) -> str:
    """Format a zero-to-one rate as a percentage."""

    return f"{value:.1%}"


def reliability_label(roc_auc: float) -> str:
    """Convert ROC AUC into a plain-language reliability label."""

    if roc_auc < 0.55:
        return "Very weak"
    if roc_auc < 0.60:
        return "Weak"
    if roc_auc < 0.70:
        return "Limited"
    if roc_auc < 0.80:
        return "Useful"
    return "Strong"


def build_campaign_ranking_chart(
    dataframe: pd.DataFrame,
    metric_column: str,
    metric_label: str,
    axis_format: str,
    lower_is_better: bool,
    benchmark: float,
) -> alt.LayerChart:
    """Build a campaign-ranking chart with a portfolio benchmark."""

    sort_order = "ascending" if lower_is_better else "descending"
    operator = "<=" if lower_is_better else ">="
    condition = f"datum.{metric_column} {operator} {benchmark}"

    bars = (
        alt.Chart(dataframe)
        .mark_bar(cornerRadiusEnd=5, size=24)
        .encode(
            x=alt.X(
                f"{metric_column}:Q",
                title=metric_label,
                axis=alt.Axis(format=axis_format),
            ),
            y=alt.Y(
                "campaign_name:N",
                title=None,
                sort=alt.SortField(field=metric_column, order=sort_order),
                axis=alt.Axis(labelLimit=220, labelPadding=8),
            ),
            color=alt.condition(
                condition,
                alt.value("#16a34a"),
                alt.value("#f59e0b"),
            ),
            tooltip=[
                alt.Tooltip("campaign_id:N", title="Campaign ID"),
                alt.Tooltip("campaign_name:N", title="Campaign"),
                alt.Tooltip("campaign_type:N", title="Type"),
                alt.Tooltip(
                    f"{metric_column}:Q",
                    title=metric_label,
                    format=axis_format,
                ),
                alt.Tooltip(
                    "attributed_users:Q",
                    title="Attributed users",
                    format=",",
                ),
            ],
        )
    )

    benchmark_line = (
        alt.Chart(pd.DataFrame({"benchmark": [benchmark]}))
        .mark_rule(color="#475569", strokeDash=[6, 5], strokeWidth=2)
        .encode(
            x=alt.X("benchmark:Q"),
            tooltip=[
                alt.Tooltip(
                    "benchmark:Q",
                    title="Portfolio benchmark",
                    format=axis_format,
                )
            ],
        )
    )

    return (bars + benchmark_line).properties(height=430)


def build_spend_revenue_chart(dataframe: pd.DataFrame) -> alt.LayerChart:
    """Compare campaign spend with attributed revenue."""

    maximum_value = float(
        max(
            dataframe["total_spend"].max(),
            dataframe["total_sale_revenue"].max(),
        )
    )

    break_even_data = pd.DataFrame(
        {
            "spend": [0.0, maximum_value],
            "revenue": [0.0, maximum_value],
        }
    )

    points = (
        alt.Chart(dataframe)
        .mark_circle(size=260, opacity=0.85, stroke="white", strokeWidth=1)
        .encode(
            x=alt.X(
                "total_spend:Q",
                title="Total spend (EUR)",
                axis=alt.Axis(format=",.0f"),
            ),
            y=alt.Y(
                "total_sale_revenue:Q",
                title="Total sale revenue (EUR)",
                axis=alt.Axis(format=",.0f"),
            ),
            color=alt.Color(
                "campaign_type:N",
                title="Campaign type",
                scale=alt.Scale(scheme="tableau10"),
            ),
            tooltip=[
                alt.Tooltip("campaign_id:N", title="Campaign ID"),
                alt.Tooltip("campaign_name:N", title="Campaign"),
                alt.Tooltip("campaign_type:N", title="Type"),
                alt.Tooltip("total_spend:Q", title="Spend (EUR)", format=",.2f"),
                alt.Tooltip(
                    "total_sale_revenue:Q",
                    title="Revenue (EUR)",
                    format=",.2f",
                ),
                alt.Tooltip(
                    "total_revenue_roas:Q",
                    title="ROAS",
                    format=".2f",
                ),
                alt.Tooltip("sale_users:Q", title="Sale users", format=","),
            ],
        )
    )

    break_even_line = (
        alt.Chart(break_even_data)
        .mark_line(color="#dc2626", strokeDash=[6, 5], strokeWidth=2)
        .encode(x="spend:Q", y="revenue:Q")
    )

    return (points + break_even_line).properties(height=450)


def prepare_factor_data(
    target_features: pd.DataFrame,
    target_references: pd.DataFrame,
) -> pd.DataFrame:
    """Prepare the strongest positive and negative model factors."""

    positive = (
        target_features[target_features["coefficient"] > 0]
        .nlargest(5, "absolute_importance")
        .copy()
    )

    negative = (
        target_features[target_features["coefficient"] < 0]
        .nlargest(5, "absolute_importance")
        .copy()
    )

    factors = pd.concat([positive, negative], ignore_index=True)

    reference_lookup = target_references.set_index("predictor")[
        "reference_category"
    ].to_dict()

    factors["factor_label"] = (
        factors["predictor"]
        .map(FACTOR_LABELS)
        .fillna(factors["predictor"])
        + ": "
        + factors["category"].astype(str)
    )

    factors["comparison_group"] = factors["predictor"].map(reference_lookup)

    return factors


def build_factor_chart(dataframe: pd.DataFrame) -> alt.Chart:
    """Show factors linked to higher or lower estimated conversion."""

    return (
        alt.Chart(dataframe)
        .mark_bar(cornerRadiusEnd=4, size=22)
        .encode(
            x=alt.X(
                "coefficient:Q",
                title="Estimated association relative to the comparison group",
            ),
            y=alt.Y(
                "factor_label:N",
                title=None,
                sort=alt.SortField(field="coefficient", order="descending"),
                axis=alt.Axis(labelLimit=320, labelPadding=8),
            ),
            color=alt.condition(
                "datum.coefficient >= 0",
                alt.value("#16a34a"),
                alt.value("#dc2626"),
            ),
            tooltip=[
                alt.Tooltip("factor_label:N", title="Factor"),
                alt.Tooltip(
                    "comparison_group:N",
                    title="Compared with",
                ),
                alt.Tooltip(
                    "odds_ratio:Q",
                    title="Relative estimated odds",
                    format=".2f",
                ),
                alt.Tooltip(
                    "direction:N",
                    title="Direction",
                ),
            ],
        )
        .properties(height=430)
    )


try:
    (
        campaigns,
        portfolio_df,
        model_metrics,
        feature_importance,
        reference_categories,
    ) = load_data()
except duckdb.Error as error:
    st.error("The prepared dashboard tables are not available.")
    st.code("make build\nmake train\nmake app", language="bash")
    st.caption(str(error))
    st.stop()

if campaigns.empty or portfolio_df.empty:
    st.error("The prepared campaign tables contain no rows.")
    st.stop()

portfolio = portfolio_df.iloc[0]


st.title("Subscription Marketing Analytics")

st.markdown(
    """
    This app answers two questions for the marketing team:

    1. **Which campaigns are performing best and worst?**
    2. **What predicts whether a user will start a trial or convert to a sale?**
    """
)

st.markdown(
    """
    <div class="decision-box">
        Start with the recommended budget actions. Supporting methodology
        and model details are available in the final sections.
    </div>
    """,
    unsafe_allow_html=True,
)


st.sidebar.header("Campaign view controls")
st.sidebar.caption("These controls affect the Campaign decisions tab.")

campaign_type_options = [
    "All campaign types",
    *sorted(campaigns["campaign_type"].dropna().unique()),
]

selected_campaign_type = st.sidebar.selectbox(
    "Campaign type",
    campaign_type_options,
)

selected_metric_label = st.sidebar.selectbox(
    "Campaign ranking",
    list(METRIC_OPTIONS.keys()),
)

if selected_campaign_type == "All campaign types":
    filtered_campaigns = campaigns.copy()
else:
    filtered_campaigns = campaigns[
        campaigns["campaign_type"] == selected_campaign_type
    ].copy()

metric_config = METRIC_OPTIONS[selected_metric_label]
metric_column = metric_config["column"]

campaign_tab, influence_tab, notes_tab = st.tabs(
    [
        "Campaign decisions",
        "What influences conversion?",
        "How the analysis works",
    ]
)


with campaign_tab:
    st.subheader("Portfolio performance")

    kpi_1, kpi_2, kpi_3 = st.columns(3)

    with kpi_1:
        st.metric("Total spend", format_amount(portfolio["total_spend"]))

    with kpi_2:
        st.metric(
            "Total sale revenue",
            format_amount(portfolio["total_sale_revenue"]),
        )

    with kpi_3:
        st.metric(
            "Portfolio ROAS",
            f"{portfolio['total_revenue_roas']:.2f}",
            help="Revenue returned for each unit of spend.",
        )

    kpi_4, kpi_5, kpi_6 = st.columns(3)

    with kpi_4:
        st.metric(
            "Attributed users",
            f"{int(portfolio['attributed_users']):,}",
        )

    with kpi_5:
        st.metric("Trial rate", format_percent(portfolio["trial_rate"]))

    with kpi_6:
        st.metric("Sale rate", format_percent(portfolio["sale_rate"]))

    best_roas = campaigns.loc[campaigns["total_revenue_roas"].idxmax()]
    lowest_cpt = campaigns.loc[campaigns["cost_per_trial"].idxmin()]
    revenue_leader = campaigns.loc[campaigns["total_sale_revenue"].idxmax()]
    weakest_roas = campaigns.loc[campaigns["total_revenue_roas"].idxmin()]

    st.divider()
    st.subheader("Recommended actions")

    action_1, action_2, action_3 = st.columns(3)

    with action_1:
        st.metric("Best efficiency", f"{best_roas['total_revenue_roas']:.2f} ROAS")
        st.caption(best_roas["campaign_name"])
        st.success("Test a controlled budget increase.")

    with action_2:
        st.metric(
            "Largest revenue contribution",
            format_amount(revenue_leader["total_sale_revenue"]),
        )
        st.caption(revenue_leader["campaign_name"])
        st.info("Protect scale while monitoring acquisition cost.")

    with action_3:
        st.metric("Weakest efficiency", f"{weakest_roas['total_revenue_roas']:.2f} ROAS")
        st.caption(weakest_roas["campaign_name"])
        st.warning("Review targeting, creative, and budget allocation.")

    st.markdown(
        f"""
        **Decision summary:** {best_roas['campaign_name']} has the strongest
        total ROAS. {lowest_cpt['campaign_name']} has the lowest cost per
        trial. {revenue_leader['campaign_name']} produces the most total
        revenue. {weakest_roas['campaign_name']} has the weakest ROAS and
        should be reviewed before more budget is added.
        """
    )

    st.subheader("Campaign ranking")
    st.caption(
        "Green bars perform better than the portfolio benchmark. "
        "For cost metrics, lower values are better."
    )

    st.altair_chart(
        build_campaign_ranking_chart(
            dataframe=filtered_campaigns,
            metric_column=metric_column,
            metric_label=selected_metric_label,
            axis_format=metric_config["axis_format"],
            lower_is_better=metric_config["lower_is_better"],
            benchmark=float(portfolio[metric_column]),
        )
    )

    st.subheader("Spend and revenue scale")

    st.altair_chart(
        build_spend_revenue_chart(campaigns)
    )

    st.caption(
        "The dashed red line represents break-even ROAS of 1. "
        "Campaigns above the line generated more sale revenue than spend."
    )

    st.subheader("Campaign detail")

    campaign_table = campaigns[
        [
            "campaign_id",
            "campaign_name",
            "campaign_type",
            "attributed_users",
            "trial_rate",
            "sale_rate",
            "total_spend",
            "cost_per_trial",
            "cost_per_sale",
            "total_sale_revenue",
            "total_revenue_roas",
        ]
    ].copy()

    campaign_table["campaign"] = (
        campaign_table["campaign_id"]
        + " — "
        + campaign_table["campaign_name"]
    )
    campaign_table["trial_rate_pct"] = campaign_table["trial_rate"] * 100
    campaign_table["sale_rate_pct"] = campaign_table["sale_rate"] * 100

    campaign_table = campaign_table[
        [
            "campaign",
            "campaign_type",
            "attributed_users",
            "trial_rate_pct",
            "sale_rate_pct",
            "total_spend",
            "cost_per_trial",
            "cost_per_sale",
            "total_sale_revenue",
            "total_revenue_roas",
        ]
    ].sort_values(
        "total_revenue_roas",
        ascending=False,
    )

    st.dataframe(
        campaign_table,
        hide_index=True,
        width="stretch",
        column_config={
            "campaign": st.column_config.TextColumn("Campaign"),
            "campaign_type": st.column_config.TextColumn("Type"),
            "attributed_users": st.column_config.NumberColumn(
                "Attributed users",
                format="%d",
            ),
            "trial_rate_pct": st.column_config.NumberColumn(
                "Trial rate (%)",
                format="%.1f",
            ),
            "sale_rate_pct": st.column_config.NumberColumn(
                "Sale rate (%)",
                format="%.1f",
            ),
            "total_spend": st.column_config.NumberColumn(
                "Spend",
                format="%.2f",
            ),
            "cost_per_trial": st.column_config.NumberColumn(
                "Cost per trial",
                format="%.2f",
            ),
            "cost_per_sale": st.column_config.NumberColumn(
                "Cost per sale",
                format="%.2f",
            ),
            "total_sale_revenue": st.column_config.NumberColumn(
                "Total revenue",
                format="%.2f",
            ),
            "total_revenue_roas": st.column_config.NumberColumn(
                "Total ROAS",
                format="%.2f",
            ),
        },
    )

    with st.expander("Show full campaign audit table"):
        full_campaign_table = campaigns[
            [
                "campaign_id",
                "campaign_name",
                "campaign_type",
                "attributed_users",
                "trial_users",
                "sale_users",
                "trial_rate",
                "sale_rate",
                "total_spend",
                "cost_per_trial",
                "cost_per_sale",
                "initial_sale_revenue",
                "total_sale_revenue",
                "initial_revenue_roas",
                "total_revenue_roas",
            ]
        ].copy()

        full_campaign_table["trial_rate_pct"] = (
            full_campaign_table["trial_rate"] * 100
        )
        full_campaign_table["sale_rate_pct"] = (
            full_campaign_table["sale_rate"] * 100
        )
        full_campaign_table = full_campaign_table.drop(
            columns=["trial_rate", "sale_rate"]
        ).sort_values(
            "total_revenue_roas",
            ascending=False,
        )

        st.dataframe(
            full_campaign_table,
            hide_index=True,
            width="stretch",
            column_config={
                "campaign_id": st.column_config.TextColumn("Campaign ID"),
                "campaign_name": st.column_config.TextColumn("Campaign"),
                "campaign_type": st.column_config.TextColumn("Type"),
                "attributed_users": st.column_config.NumberColumn(
                    "Attributed users",
                    format="%d",
                ),
                "trial_users": st.column_config.NumberColumn(
                    "Trial users",
                    format="%d",
                ),
                "sale_users": st.column_config.NumberColumn(
                    "Sale users",
                    format="%d",
                ),
                "trial_rate_pct": st.column_config.NumberColumn(
                    "Trial rate (%)",
                    format="%.1f",
                ),
                "sale_rate_pct": st.column_config.NumberColumn(
                    "Sale rate (%)",
                    format="%.1f",
                ),
                "total_spend": st.column_config.NumberColumn(
                    "Spend (EUR)",
                    format="%.2f",
                ),
                "cost_per_trial": st.column_config.NumberColumn(
                    "Cost per trial (EUR)",
                    format="%.2f",
                ),
                "cost_per_sale": st.column_config.NumberColumn(
                    "Cost per sale (EUR)",
                    format="%.2f",
                ),
                "initial_sale_revenue": st.column_config.NumberColumn(
                    "Initial revenue (EUR)",
                    format="%.2f",
                ),
                "total_sale_revenue": st.column_config.NumberColumn(
                    "Total revenue (EUR)",
                    format="%.2f",
                ),
                "initial_revenue_roas": st.column_config.NumberColumn(
                    "Initial ROAS",
                    format="%.2f",
                ),
                "total_revenue_roas": st.column_config.NumberColumn(
                    "Total ROAS",
                    format="%.2f",
                ),
            },
        )

    st.caption(
        "All monetary values are shown in EUR."
    )


with influence_tab:
    st.subheader("Which factors are linked to trial and sale outcomes?")

    st.markdown(
        """
        The strongest relationships appear in the onboarding experience.
        However, the available user and acquisition factors do **not**
        reliably identify which individual users will convert. Use these
        findings to guide experiments, not automated targeting.
        """
    )

    selected_target = st.radio(
        "Outcome",
        list(TARGET_LABELS.keys()),
        format_func=lambda value: TARGET_LABELS[value],
        horizontal=True,
    )

    selected_metrics = model_metrics[model_metrics["target"] == selected_target]

    if selected_metrics.empty:
        st.warning("No model results are available for this outcome.")
    else:
        metric = selected_metrics.iloc[0]

        if selected_target == "started_trial":
            recall_label = "Actual trial starters found"
            precision_label = "Flagged users who started a trial"
            recall_help = (
                "Share of users who eventually started a trial and were "
                "identified by the model."
            )
            precision_help = (
                "Share of users flagged by the model who actually started "
                "a trial."
            )
        else:
            recall_label = "Actual buyers found"
            precision_label = "Flagged users who bought"
            recall_help = (
                "Share of users who eventually bought and were identified "
                "by the model."
            )
            precision_help = (
                "Share of users flagged by the model who actually bought."
            )

        manager_kpi_1, manager_kpi_2, manager_kpi_3, manager_kpi_4 = st.columns(4)

        with manager_kpi_1:
            st.metric("Model reliability", reliability_label(metric["roc_auc"]))

        with manager_kpi_2:
            st.metric(
                recall_label,
                format_percent(metric["recall"]),
                help=recall_help,
            )

        with manager_kpi_3:
            st.metric(
                precision_label,
                format_percent(metric["precision"]),
                help=precision_help,
            )

        with manager_kpi_4:
            st.metric(
                "Test users flagged",
                format_percent(metric["predicted_positive_rate"]),
            )

        if metric["roc_auc"] < 0.60:
            st.warning(
                "The model is only slightly better than random ranking. "
                "It flags most users, so it is not suitable for narrow "
                "individual targeting."
            )

        target_features = feature_importance[
            feature_importance["target"] == selected_target
        ].copy()

        target_references = reference_categories[
            reference_categories["target"] == selected_target
        ].copy()

        factor_data = prepare_factor_data(target_features, target_references)

        strongest_predictor = (
            factor_data.iloc[0]["predictor"] if not factor_data.empty else None
        )

        if strongest_predictor:
            st.info(
                f"The strongest signal comes from "
                f"{PREDICTOR_LABELS.get(strongest_predictor, strongest_predictor).lower()}."
            )

        st.subheader("Factors associated with higher or lower likelihood")

        st.altair_chart(
            build_factor_chart(factor_data)
        )

        st.caption(
            "Bars to the right indicate higher estimated likelihood than the "
            "comparison group. Bars to the left indicate lower estimated "
            "likelihood. These relationships do not prove causation."
        )

        positive_factors = factor_data[factor_data["coefficient"] > 0].copy()
        negative_factors = factor_data[factor_data["coefficient"] < 0].copy()

        higher_column, lower_column = st.columns(2)

        with higher_column:
            st.markdown("**Associated with higher likelihood**")

            higher_table = positive_factors[
                ["factor_label", "comparison_group", "odds_ratio"]
            ].copy()

            st.dataframe(
                higher_table,
                hide_index=True,
                width="stretch",
                column_config={
                    "factor_label": st.column_config.TextColumn("Factor"),
                    "comparison_group": st.column_config.TextColumn(
                        "Compared with"
                    ),
                    "odds_ratio": st.column_config.NumberColumn(
                        "Relative estimated odds",
                        format="%.2f×",
                    ),
                },
            )

        with lower_column:
            st.markdown("**Associated with lower likelihood**")

            lower_table = negative_factors[
                ["factor_label", "comparison_group", "odds_ratio"]
            ].copy()

            st.dataframe(
                lower_table,
                hide_index=True,
                width="stretch",
                column_config={
                    "factor_label": st.column_config.TextColumn("Factor"),
                    "comparison_group": st.column_config.TextColumn(
                        "Compared with"
                    ),
                    "odds_ratio": st.column_config.NumberColumn(
                        "Relative estimated odds",
                        format="%.2f×",
                    ),
                },
            )

        with st.expander("Technical model details"):
            st.markdown(
                "These details support review and validation. They are not "
                "required for the main marketing decision."
            )

            technical_1, technical_2, technical_3, technical_4 = st.columns(4)

            with technical_1:
                st.metric("ROC AUC", f"{metric['roc_auc']:.3f}")

            with technical_2:
                st.metric("Precision", format_percent(metric["precision"]))

            with technical_3:
                st.metric("Recall", format_percent(metric["recall"]))

            with technical_4:
                st.metric("F1 score", f"{metric['f1_score']:.3f}")

            st.caption(
                f"The selected probability threshold is "
                f"{metric['prediction_threshold']:.0%}. The final test period "
                f"starts on {metric['test_start_date']}."
            )

            review_left, review_right = st.columns(2)

            with review_left:
                st.markdown("**Comparison groups**")

                comparison_table = target_references[
                    ["predictor", "reference_category"]
                ].copy()

                comparison_table["predictor"] = (
                    comparison_table["predictor"]
                    .map(PREDICTOR_LABELS)
                    .fillna(comparison_table["predictor"])
                )

                st.dataframe(
                    comparison_table,
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "predictor": st.column_config.TextColumn("Factor"),
                        "reference_category": st.column_config.TextColumn(
                            "Comparison group"
                        ),
                    },
                )

            with review_right:
                st.markdown("**Test results by user count**")

                confusion_table = pd.DataFrame(
                    {
                        "Result": [
                            "Converters correctly flagged",
                            "Non-converters incorrectly flagged",
                            "Converters missed",
                            "Non-converters correctly rejected",
                        ],
                        "Users": [
                            int(metric["true_positive"]),
                            int(metric["false_positive"]),
                            int(metric["false_negative"]),
                            int(metric["true_negative"]),
                        ],
                    }
                )

                st.dataframe(
                    confusion_table,
                    hide_index=True,
                    width="stretch",
                )


with notes_tab:
    st.subheader("How the analysis works")

    st.markdown(
        """
        **Campaign performance**

        - Users and revenue are assigned to the campaign recorded on the
          first onboarding event.
        - Cost per trial equals campaign spend divided by trial users.
        - ROAS equals attributed sale revenue divided by campaign spend.
        - `C999` remains in user-level analysis but is excluded from campaign
          efficiency rankings because it has no spend or campaign metadata.

        **Revenue**

        - Initial revenue sums revenue recorded at the earliest sale timestamp.
        - Total revenue includes all recorded sale events with positive revenue.
        - A user with more than one sale still counts as one converted user.

        **Conversion factors**

        - The models use gender, country, campaign, onboarding experience,
          and acquisition weekday.
        - The models do not use trial events, sale events, revenue, or other
          future information.
        - Earlier users train the model, a middle period selects the decision
          threshold, and the latest users test the final result.
        - Model relationships show association. They do not prove that a
          factor caused the outcome.
        """
    )

    st.info(
        "The app performs no raw-data cleaning and no cross-source joins. "
        "Those steps occur in the dbt pipeline."
    )