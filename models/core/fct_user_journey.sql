with activity as (

    select *
    from {{ ref('stg_user_activity') }}

),

user_profiles as (

    select *
    from {{ ref('stg_dim_user') }}

),

onboarding as (

    select
        user_id,
        event_at as onboarding_at,
        attribution_date,
        onboarding_name,
        campaign_id

    from activity
    where event_type = 'start_onboarding'

),

trials as (

    select
        user_id,
        min(event_at) as trial_at,
        count(*) as trial_event_count

    from activity
    where event_type = 'start_trial'
    group by user_id

),

first_sale as (

    select
        user_id,
        min(event_at) as first_sale_at

    from activity
    where event_type = 'sale'
    group by user_id

),

sales as (

    select
        activity.user_id,
        first_sale.first_sale_at,

        sum(
            case
                when activity.event_at = first_sale.first_sale_at
                    then activity.revenue_amount
                else 0
            end
        ) as initial_sale_revenue,

        sum(activity.revenue_amount) as total_sale_revenue,
        count(*) as sale_event_count

    from activity
    inner join first_sale
        on activity.user_id = first_sale.user_id

    where activity.event_type = 'sale'

    group by
        activity.user_id,
        first_sale.first_sale_at

),

final as (

    select
        user_profiles.user_id,
        user_profiles.gender,
        user_profiles.country,

        onboarding.campaign_id,
        onboarding.attribution_date,
        onboarding.onboarding_name,
        onboarding.onboarding_at,

        trials.trial_at,
        sales.first_sale_at,

        case
            when trials.trial_at is not null then 1
            else 0
        end as started_trial,

        case
            when sales.first_sale_at is not null then 1
            else 0
        end as made_sale,

        case
            when sales.first_sale_at is not null
             and trials.trial_at is null then 1
            else 0
        end as sale_without_trial,

        coalesce(trials.trial_event_count, 0)
            as trial_event_count,

        coalesce(sales.sale_event_count, 0)
            as sale_event_count,

        sales.initial_sale_revenue,

        coalesce(sales.total_sale_revenue, 0.0)
            as total_sale_revenue,

        case
            when coalesce(sales.sale_event_count, 0) > 1 then 1
            else 0
        end as has_multiple_sales,

        user_profiles.has_gender_conflict,
        user_profiles.has_country_conflict,
        user_profiles.has_campaign_conflict

    from user_profiles

    left join onboarding
        on user_profiles.user_id = onboarding.user_id

    left join trials
        on user_profiles.user_id = trials.user_id

    left join sales
        on user_profiles.user_id = sales.user_id

)

select *
from final