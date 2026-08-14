with feature_rows as (

    select *
    from {{ ref('user_features') }}

),

journey_rows as (

    select
        user_id,
        started_trial,
        made_sale
    from {{ ref('fct_user_journey') }}

),

invalid_targets as (

    select
        feature_rows.user_id

    from feature_rows

    inner join journey_rows
        on feature_rows.user_id = journey_rows.user_id

    where
        feature_rows.started_trial
            <> journey_rows.started_trial

        or feature_rows.made_sale
            <> journey_rows.made_sale

),

row_counts as (

    select
        (
            select count(*)
            from feature_rows
        ) as feature_row_count,

        (
            select count(*)
            from journey_rows
        ) as journey_row_count

)

select
    'target_mismatch' as issue_type,
    user_id

from invalid_targets

union all

select
    'row_count_mismatch' as issue_type,
    null as user_id

from row_counts

where feature_row_count <> journey_row_count