with user_journey as (

    select *
    from {{ ref('fct_user_journey') }}

),

campaigns as (

    select *
    from {{ ref('stg_marketing_campaigns') }}

),

final as (

    select
        user_journey.user_id,
        user_journey.attribution_date,

        user_journey.gender,
        user_journey.country,

        user_journey.campaign_id,

        user_journey.campaign_id
        || ' - '
        || coalesce(
            campaigns.campaign_name,
            'Unmapped campaign'
        ) as campaign_label,

        user_journey.onboarding_name,

        lower(
            strftime(
                user_journey.attribution_date,
                '%A'
            )
        ) as attribution_weekday,

        cast(
            extract(
                month from user_journey.attribution_date
            ) as integer
        ) as attribution_month,

        user_journey.started_trial,
        user_journey.made_sale

    from user_journey

    left join campaigns
        on user_journey.campaign_id = campaigns.campaign_id

)

select *
from final