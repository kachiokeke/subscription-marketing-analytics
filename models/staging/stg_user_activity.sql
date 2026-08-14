with source as (

    select *
    from {{ source('raw', 'user_activity') }}

),

normalized as (

    select
        trim(cast(user_id as varchar)) as user_id,

        lower(
            trim(cast(event_type as varchar))
        ) as event_type,

        cast(event_date as timestamp) as event_at,

        case
            when lower(
                trim(cast(event_type as varchar))
            ) = 'sale'
                then cast(revenue_amount as double)

            else null
        end as revenue_amount,

        cast(attribution_date as date) as attribution_date,

        coalesce(
            nullif(
                lower(
                    trim(cast(onboarding_name as varchar))
                ),
                ''
            ),
            'unknown'
        ) as onboarding_name,

        cast(dt as date) as source_date,

        nullif(
            upper(trim(cast(campaign_id as varchar))),
            ''
        ) as campaign_id

    from source

),

final as (

    select
        {{ dbt_utils.generate_surrogate_key([
            'user_id',
            'event_type',
            'event_at',
            'revenue_amount',
            'attribution_date',
            'onboarding_name',
            'campaign_id'
        ]) }} as activity_id,

        user_id,
        event_type,
        event_at,
        revenue_amount,
        attribution_date,
        onboarding_name,
        source_date,
        campaign_id

    from normalized

)

select *
from final