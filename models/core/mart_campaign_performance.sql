with campaigns as (

    select *
    from {{ ref('stg_marketing_campaigns') }}

),

user_outcomes_by_date as (

    select
        user_journey.campaign_id,
        user_journey.attribution_date,

        count(*) as attributed_users,
        sum(user_journey.started_trial) as trial_users,
        sum(user_journey.made_sale) as sale_users,
        sum(user_journey.sale_without_trial) as sale_without_trial_users,

        sum(
            coalesce(user_journey.initial_sale_revenue, 0.0)
        ) as initial_sale_revenue,

        sum(user_journey.total_sale_revenue) as total_sale_revenue

    from {{ ref('fct_user_journey') }} as user_journey

    inner join campaigns
        on user_journey.campaign_id = campaigns.campaign_id

    group by
        user_journey.campaign_id,
        user_journey.attribution_date

),

campaign_spend_by_date as (

    select
        campaign_id,
        spend_date,
        sum(spend_amount) as daily_spend

    from {{ ref('stg_marketing_spend') }}

    group by
        campaign_id,
        spend_date

),

attributed_daily_performance as (

    select
        user_outcomes_by_date.campaign_id,
        user_outcomes_by_date.attribution_date,
        campaign_spend_by_date.spend_date,
        campaign_spend_by_date.daily_spend,

        user_outcomes_by_date.attributed_users,
        user_outcomes_by_date.trial_users,
        user_outcomes_by_date.sale_users,
        user_outcomes_by_date.sale_without_trial_users,
        user_outcomes_by_date.initial_sale_revenue,
        user_outcomes_by_date.total_sale_revenue

    from user_outcomes_by_date

    inner join campaign_spend_by_date
        on user_outcomes_by_date.campaign_id
            = campaign_spend_by_date.campaign_id
        and user_outcomes_by_date.attribution_date
            = campaign_spend_by_date.spend_date

),

campaign_rollup as (

    select
        campaign_id,

        min(spend_date) as first_spend_date,
        max(spend_date) as last_spend_date,
        count(*) as spend_day_count,
        sum(daily_spend) as total_spend,

        sum(attributed_users) as attributed_users,
        sum(trial_users) as trial_users,
        sum(sale_users) as sale_users,
        sum(sale_without_trial_users) as sale_without_trial_users,
        sum(initial_sale_revenue) as initial_sale_revenue,
        sum(total_sale_revenue) as total_sale_revenue

    from attributed_daily_performance
    group by campaign_id

),

final as (

    select
        campaigns.campaign_id,
        campaigns.campaign_name,
        campaigns.campaign_type,

        coalesce(campaign_rollup.attributed_users, 0) as attributed_users,
        coalesce(campaign_rollup.trial_users, 0) as trial_users,
        coalesce(campaign_rollup.sale_users, 0) as sale_users,
        coalesce(
            campaign_rollup.sale_without_trial_users,
            0
        ) as sale_without_trial_users,

        campaign_rollup.first_spend_date,
        campaign_rollup.last_spend_date,
        campaign_rollup.spend_day_count,
        campaign_rollup.total_spend,

        coalesce(
            campaign_rollup.initial_sale_revenue,
            0.0
        ) as initial_sale_revenue,

        coalesce(
            campaign_rollup.total_sale_revenue,
            0.0
        ) as total_sale_revenue,

        cast(
            coalesce(campaign_rollup.trial_users, 0)
            as double
        )
        / nullif(
            coalesce(campaign_rollup.attributed_users, 0),
            0
        ) as trial_rate,

        cast(
            coalesce(campaign_rollup.sale_users, 0)
            as double
        )
        / nullif(
            coalesce(campaign_rollup.attributed_users, 0),
            0
        ) as sale_rate,

        campaign_rollup.total_spend
        / nullif(
            coalesce(campaign_rollup.trial_users, 0),
            0
        ) as cost_per_trial,

        campaign_rollup.total_spend
        / nullif(
            coalesce(campaign_rollup.sale_users, 0),
            0
        ) as cost_per_sale,

        coalesce(
            campaign_rollup.initial_sale_revenue,
            0.0
        )
        / nullif(
            campaign_rollup.total_spend,
            0
        ) as initial_revenue_roas,

        coalesce(
            campaign_rollup.total_sale_revenue,
            0.0
        )
        / nullif(
            campaign_rollup.total_spend,
            0
        ) as total_revenue_roas

    from campaigns

    left join campaign_rollup
        on campaigns.campaign_id = campaign_rollup.campaign_id

)

select *
from final
