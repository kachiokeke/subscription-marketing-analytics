"""Data exploration scratchpad.

# Profile the raw sources before building the dbt transformation models.

Purpose: profile the four raw CSVs. Find dupes, inconsistencies, unknown
foreign keys, outliers, missing values, and anything else that will affect
downstream modeling decisions. Document what you find in DECISIONS.md under
"Exploration findings" (a required deliverable).

Run: `make explore`  (or `.venv/bin/python explore.py`)

The example query below shows one way to load and profile the sources. Extend
it. Add your own queries. This file is a scratchpad, so feel free to reorganize
or replace it entirely.
"""

from pathlib import Path

import duckdb


DATA = Path(__file__).parent / "data" / "raw"
con = duckdb.connect(":memory:")

for name in ["marketing_spend", "marketing_campaigns", "dim_user", "user_activity"]:
    con.execute(f"create view {name} as select * from read_csv_auto('{DATA / (name + '.csv')}')")


# -----------------------------------------------------------------------------
# Example: basic row counts. Extend from here.
# -----------------------------------------------------------------------------

for tbl in ["marketing_spend", "marketing_campaigns", "dim_user", "user_activity"]:
    n = con.execute(f"select count(*) from {tbl}").fetchone()[0]
    print(f"{tbl}: {n:,} rows")

TABLES = [
    "marketing_spend",
    "marketing_campaigns",
    "dim_user",
    "user_activity",
]


def print_section(title: str) -> None:
    """Print a clear section heading."""
    print(f"\n{'=' * 80}")
    print(title)
    print("=" * 80)


def show_query(title: str, sql: str) -> None:
    """Run a query and print its result."""
    print(f"\n{title}")
    result = con.execute(sql).fetchdf()
    print(result.to_string(index=False))


print_section("TABLE STRUCTURE")

for table in TABLES:
    show_query(
        f"{table}: columns and data types",
        f"describe {table}",
    )

print_section("NULL COUNTS")

for table in TABLES:
    columns = [
        row[0]
        for row in con.execute(f"describe {table}").fetchall()
    ]

    null_expressions = ",\n".join(
        f'sum(case when "{column}" is null then 1 else 0 end) '
        f'as "{column}"'
        for column in columns
    )

    show_query(
        f"{table}: null counts",
        f"select {null_expressions} from {table}",
    )

print_section("EXACT DUPLICATE ROWS")

for table in TABLES:
    show_query(
        f"{table}: exact duplicate rows",
        f"""
        with row_counts as (
            select
                (select count(*) from {table}) as row_count,
                (
                    select count(*)
                    from (
                        select distinct *
                        from {table}
                    ) as distinct_rows
                ) as distinct_row_count
        )

        select
            row_count,
            distinct_row_count,
            row_count - distinct_row_count as exact_duplicate_rows
        from row_counts
        """,
    )

print_section("DIM_USER KEY DUPLICATES")

show_query(
    "dim_user: duplicate user_id summary",
    """
    with duplicate_users as (
        select
            user_id,
            count(*) as row_count,
            count(
                distinct coalesce(trim(gender), '__NULL__')
            ) as gender_value_count,
            count(
                distinct coalesce(trim(country), '__NULL__')
            ) as country_value_count,
            count(
                distinct coalesce(trim(campaign_id), '__NULL__')
            ) as campaign_value_count
        from dim_user
        group by user_id
        having count(*) > 1
    )

    select
        count(*) as duplicated_user_ids,
        sum(row_count - 1) as extra_rows,
        sum(
            case
                when gender_value_count > 1
                  or country_value_count > 1
                  or campaign_value_count > 1
                then 1
                else 0
            end
        ) as conflicting_user_ids
    from duplicate_users
    """,
)

print_section("CATEGORICAL VALUES")

CATEGORY_COLUMNS = {
    "marketing_spend": ["campaign_id"],
    "marketing_campaigns": ["campaign_type"],
    "dim_user": ["gender", "country", "campaign_id"],
    "user_activity": ["event_type", "onboarding_name", "campaign_id"],
}

for table, columns in CATEGORY_COLUMNS.items():
    for column in columns:
        show_query(
            f"{table}.{column}: value counts",
            f"""
            select
                coalesce(
                    '[' || cast("{column}" as varchar) || ']',
                    '[NULL]'
                ) as value,
                count(*) as row_count
            from {table}
            group by 1
            order by row_count desc, value
            """,
        )

print_section("DIM_USER CONFLICT DETAILS")

show_query(
    "dim_user: conflicting fields within duplicate user IDs",
    """
    with duplicate_users as (
        select
            user_id,
            count(
                distinct coalesce(trim(gender), '__NULL__')
            ) as gender_value_count,
            count(
                distinct coalesce(trim(country), '__NULL__')
            ) as country_value_count,
            count(
                distinct coalesce(trim(campaign_id), '__NULL__')
            ) as campaign_value_count
        from dim_user
        group by user_id
        having count(*) > 1
    )

    select
        sum(
            case when gender_value_count > 1 then 1 else 0 end
        ) as gender_conflicts,
        sum(
            case when country_value_count > 1 then 1 else 0 end
        ) as country_conflicts,
        sum(
            case when campaign_value_count > 1 then 1 else 0 end
        ) as campaign_conflicts
    from duplicate_users
    """,
)

print_section("RELATIONSHIP CHECKS")

show_query(
    "dim_user: campaign IDs missing from marketing_campaigns",
    """
    select
        d.campaign_id,
        count(*) as row_count,
        count(distinct d.user_id) as user_count
    from dim_user as d
    left join marketing_campaigns as c
        on d.campaign_id = c.campaign_id
    where c.campaign_id is null
    group by d.campaign_id
    order by row_count desc
    """,
)

show_query(
    "user_activity: campaign IDs missing from marketing_campaigns",
    """
    select
        a.campaign_id,
        count(*) as row_count,
        count(distinct a.user_id) as user_count
    from user_activity as a
    left join marketing_campaigns as c
        on a.campaign_id = c.campaign_id
    where c.campaign_id is null
    group by a.campaign_id
    order by row_count desc
    """,
)

show_query(
    "user_activity: user IDs missing from dim_user",
    """
    select
        count(*) as orphan_activity_rows,
        count(distinct a.user_id) as orphan_user_ids
    from user_activity as a
    left join (
        select distinct user_id
        from dim_user
    ) as d
        on a.user_id = d.user_id
    where d.user_id is null
    """,
)

print_section("MISSING VALUES BY EVENT TYPE")

show_query(
    "user_activity: revenue population by event type",
    """
    select
        event_type,
        count(*) as row_count,
        sum(
            case when revenue_amount is null then 1 else 0 end
        ) as null_revenue_rows,
        sum(
            case when revenue_amount is not null then 1 else 0 end
        ) as populated_revenue_rows,
        min(revenue_amount) as minimum_revenue,
        max(revenue_amount) as maximum_revenue
    from user_activity
    group by event_type
    order by event_type
    """,
)

show_query(
    "user_activity: missing onboarding names by event type",
    """
    select
        event_type,
        count(*) as row_count,
        sum(
            case when onboarding_name is null then 1 else 0 end
        ) as null_onboarding_rows
    from user_activity
    group by event_type
    order by event_type
    """,
)

print_section("GENDER CONFLICT CLASSIFICATION")

show_query(
    "dim_user: classification of conflicting gender values",
    """
    with raw_gender_conflicts as (
        select user_id
        from dim_user
        group by user_id
        having count(
            distinct coalesce(trim(gender), '__NULL__')
        ) > 1
    ),

    normalized_gender_values as (
        select distinct
            user_id,
            case
                when gender is null then 'unknown'
                when lower(trim(gender)) in (
                    'unknown',
                    'unknownx',
                    '?'
                ) then 'unknown'
                when lower(trim(gender)) = 'prefer_not_to_say'
                    then 'prefer_not_to_say'
                else lower(trim(gender))
            end as normalized_gender
        from dim_user
    ),

    user_gender_summary as (
        select
            user_id,
            count(*) as normalized_value_count,
            sum(
                case
                    when normalized_gender <> 'unknown' then 1
                    else 0
                end
            ) as informative_value_count,
            max(
                case
                    when normalized_gender = 'unknown' then 1
                    else 0
                end
            ) as has_unknown
        from normalized_gender_values
        group by user_id
    )

    select
        count(*) as raw_gender_conflict_users,
        sum(
            case
                when normalized_value_count = 1 then 1
                else 0
            end
        ) as resolved_by_normalization,
        sum(
            case
                when informative_value_count = 1
                 and has_unknown = 1 then 1
                else 0
            end
        ) as known_plus_unknown,
        sum(
            case
                when informative_value_count > 1 then 1
                else 0
            end
        ) as contradictory_known_values
    from raw_gender_conflicts
    inner join user_gender_summary using (user_id)
    """,
)

print_section("USER JOURNEY CHECKS")

show_query(
    "user_activity: user journey summary",
    """
    with user_journey as (
        select
            user_id,

            sum(
                case
                    when event_type = 'start_onboarding' then 1
                    else 0
                end
            ) as onboarding_events,

            sum(
                case
                    when event_type = 'start_trial' then 1
                    else 0
                end
            ) as trial_events,

            sum(
                case
                    when event_type = 'sale' then 1
                    else 0
                end
            ) as sale_events,

            min(
                case
                    when event_type = 'start_onboarding'
                    then event_date
                end
            ) as onboarding_at,

            min(
                case
                    when event_type = 'start_trial'
                    then event_date
                end
            ) as trial_at,

            min(
                case
                    when event_type = 'sale'
                    then event_date
                end
            ) as first_sale_at

        from user_activity
        group by user_id
    )

    select
        count(*) as users,

        sum(
            case when trial_at is not null then 1 else 0 end
        ) as trial_users,

        sum(
            case when first_sale_at is not null then 1 else 0 end
        ) as sale_users,

        sum(
            case
                when first_sale_at is not null
                 and trial_at is null then 1
                else 0
            end
        ) as sale_without_trial_users,

        sum(
            case
                when trial_at < onboarding_at then 1
                else 0
            end
        ) as trial_before_onboarding_users,

        sum(
            case
                when first_sale_at < onboarding_at then 1
                else 0
            end
        ) as sale_before_onboarding_users,

        sum(
            case
                when first_sale_at < trial_at then 1
                else 0
            end
        ) as sale_before_trial_users,

        sum(
            case
                when onboarding_events <> 1 then 1
                else 0
            end
        ) as users_without_one_onboarding,

        sum(
            case
                when trial_events > 1 then 1
                else 0
            end
        ) as users_with_multiple_trials,

        sum(
            case
                when sale_events > 1 then 1
                else 0
            end
        ) as users_with_multiple_sales

    from user_journey
    """,
)

print_section("USER-LEVEL CONSISTENCY")

show_query(
    "user_activity: attribute consistency within users",
    """
    with user_values as (
        select
            user_id,
            count(distinct campaign_id) as campaign_value_count,
            count(
                distinct attribution_date
            ) as attribution_date_count,
            count(
                distinct onboarding_name
            ) as onboarding_name_count,
            sum(
                case
                    when onboarding_name is null then 1
                    else 0
                end
            ) as null_onboarding_rows
        from user_activity
        group by user_id
    )

    select
        sum(
            case
                when campaign_value_count > 1 then 1
                else 0
            end
        ) as campaign_conflict_users,

        sum(
            case
                when attribution_date_count > 1 then 1
                else 0
            end
        ) as attribution_date_conflict_users,

        sum(
            case
                when onboarding_name_count > 1 then 1
                else 0
            end
        ) as onboarding_name_conflict_users,

        sum(
            case
                when onboarding_name_count = 0 then 1
                else 0
            end
        ) as users_with_no_onboarding_name,

        sum(
            case
                when onboarding_name_count = 1
                 and null_onboarding_rows > 0 then 1
                else 0
            end
        ) as users_with_partly_missing_onboarding_name

    from user_values
    """,
)

show_query(
    "C999: user overlap between sources",
    """
    with dim_c999 as (
        select distinct user_id
        from dim_user
        where campaign_id = 'C999'
    ),

    activity_c999 as (
        select distinct user_id
        from user_activity
        where campaign_id = 'C999'
    )

    select
        (
            select count(*)
            from dim_c999
        ) as dim_user_c999_users,

        (
            select count(*)
            from activity_c999
        ) as activity_c999_users,

        (
            select count(*)
            from dim_c999
            inner join activity_c999 using (user_id)
        ) as shared_c999_users
    """,
)

print_section("DATE COVERAGE")

show_query(
    "Source date ranges",
    """
    select
        'marketing_spend.date' as source_field,
        min(date)::date as minimum_date,
        max(date)::date as maximum_date
    from marketing_spend

    union all

    select
        'user_activity.attribution_date',
        min(attribution_date)::date,
        max(attribution_date)::date
    from user_activity

    union all

    select
        'user_activity.event_date',
        min(event_date)::date,
        max(event_date)::date
    from user_activity

    union all

    select
        'user_activity.dt',
        min(dt)::date,
        max(dt)::date
    from user_activity
    """,
)

show_query(
    "Users with enough time to complete the trial window",
    """
    with observation_period as (
        select
            max(cast(event_date as date)) as observation_end_date
        from user_activity
    ),

    onboarding_cohorts as (
        select
            user_id,
            min(attribution_date) as attribution_date
        from user_activity
        where event_type = 'start_onboarding'
        group by user_id
    )

    select
        observation_end_date,
        cast(
            observation_end_date - interval 14 day
            as date
        ) as mature_through_date,
        count(*) as users,
        sum(
            case
                when attribution_date
                    <= observation_end_date - interval 14 day
                then 1
                else 0
            end
        ) as mature_users,
        sum(
            case
                when attribution_date
                    > observation_end_date - interval 14 day
                then 1
                else 0
            end
        ) as immature_users,
        round(
            100.0
            * sum(
                case
                    when attribution_date
                        <= observation_end_date - interval 14 day
                    then 1
                    else 0
                end
            )
            / count(*),
            2
        ) as mature_user_percentage
    from onboarding_cohorts
    cross join observation_period
    group by observation_end_date
    """,
)

show_query(
    "Campaign and attribution dates without matching spend",
    """
    with attributed_campaign_dates as (
        select distinct
            attribution_date as date,
            campaign_id
        from user_activity
    )

    select
        a.campaign_id,
        count(*) as unmatched_date_count
    from attributed_campaign_dates as a
    left join marketing_spend as s
        on a.date = s.date
       and a.campaign_id = s.campaign_id
    where s.campaign_id is null
    group by a.campaign_id
    order by unmatched_date_count desc
    """,
)

print_section("SALE EVENT PATTERNS")

show_query(
    "Sale events per converted user",
    """
    with user_sales as (
        select
            user_id,
            count(*) as sale_events,
            sum(revenue_amount) as total_revenue
        from user_activity
        where event_type = 'sale'
        group by user_id
    )

    select
        sale_events,
        count(*) as user_count,
        round(sum(total_revenue), 2) as total_revenue
    from user_sales
    group by sale_events
    order by sale_events
    """,
)

show_query(
    "Sale revenue distribution",
    """
    select
        count(*) as sale_rows,
        sum(
            case
                when revenue_amount <= 0 then 1
                else 0
            end
        ) as non_positive_revenue_rows,
        round(min(revenue_amount), 2) as minimum_revenue,
        round(
            quantile_cont(revenue_amount, 0.25),
            2
        ) as revenue_p25,
        round(
            quantile_cont(revenue_amount, 0.50),
            2
        ) as median_revenue,
        round(
            quantile_cont(revenue_amount, 0.75),
            2
        ) as revenue_p75,
        round(
            quantile_cont(revenue_amount, 0.95),
            2
        ) as revenue_p95,
        round(
            quantile_cont(revenue_amount, 0.99),
            2
        ) as revenue_p99,
        round(max(revenue_amount), 2) as maximum_revenue
    from user_activity
    where event_type = 'sale'
    """,
)

show_query(
    "Daily campaign spend distribution",
    """
    select
        count(*) as spend_rows,
        sum(
            case
                when spend <= 0 then 1
                else 0
            end
        ) as non_positive_spend_rows,
        round(min(spend), 2) as minimum_spend,
        round(
            quantile_cont(spend, 0.25),
            2
        ) as spend_p25,
        round(
            quantile_cont(spend, 0.50),
            2
        ) as median_spend,
        round(
            quantile_cont(spend, 0.75),
            2
        ) as spend_p75,
        round(
            quantile_cont(spend, 0.95),
            2
        ) as spend_p95,
        round(
            quantile_cont(spend, 0.99),
            2
        ) as spend_p99,
        round(max(spend), 2) as maximum_spend
    from marketing_spend
    """,
)

print_section("MULTIPLE SALE VALIDATION")

show_query(
    "Timing and revenue patterns for users with two sales",
    """
    with ranked_sales as (
        select
            user_id,
            event_date,
            revenue_amount,

            row_number() over (
                partition by user_id
                order by event_date, revenue_amount
            ) as sale_number,

            count(*) over (
                partition by user_id
            ) as sale_event_count

        from user_activity
        where event_type = 'sale'
    ),

    paired_sales as (
        select
            user_id,

            max(
                case
                    when sale_number = 1 then event_date
                end
            ) as first_sale_at,

            max(
                case
                    when sale_number = 2 then event_date
                end
            ) as second_sale_at,

            max(
                case
                    when sale_number = 1 then revenue_amount
                end
            ) as first_sale_revenue,

            max(
                case
                    when sale_number = 2 then revenue_amount
                end
            ) as second_sale_revenue

        from ranked_sales
        where sale_event_count = 2
        group by user_id
    ),

    trial_dates as (
        select
            user_id,

            min(
                case
                    when event_type = 'start_trial'
                    then event_date
                end
            ) as trial_at

        from user_activity
        group by user_id
    )

    select
        count(*) as users_with_two_sales,

        sum(
            case
                when second_sale_at
                    < first_sale_at + interval 24 hour
                then 1
                else 0
            end
        ) as second_sale_within_24_hours,

        sum(
            case
                when second_sale_at
                    >= first_sale_at + interval 24 hour
                 and second_sale_at
                    <= first_sale_at + interval 48 hour
                then 1
                else 0
            end
        ) as second_sale_between_24_and_48_hours,

        sum(
            case
                when trial_at is not null
                 and first_sale_at = trial_at + interval 14 day
                then 1
                else 0
            end
        ) as first_sale_exactly_14_days_after_trial,

        sum(
            case
                when trial_at is null then 1
                else 0
            end
        ) as two_sale_users_without_trial,

        sum(
            case
                when first_sale_revenue = second_sale_revenue
                then 1
                else 0
            end
        ) as sales_with_equal_revenue

    from paired_sales
    left join trial_dates using (user_id)
    """,
)

show_query(
    "Attribution and source date consistency",
    """
    select
        count(*) as activity_rows,

        sum(
            case
                when cast(dt as date) = attribution_date
                then 1
                else 0
            end
        ) as dt_matches_attribution_date,

        sum(
            case
                when event_type = 'start_onboarding'
                 and cast(event_date as date) = attribution_date
                then 1
                else 0
            end
        ) as onboarding_matches_attribution_date,

        sum(
            case
                when event_type = 'start_onboarding'
                then 1
                else 0
            end
        ) as onboarding_rows

    from user_activity
    """,
)

con.close()
