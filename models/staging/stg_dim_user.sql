with source as (

    select *
    from {{ source('raw', 'dim_user') }}

),

normalized as (

    select distinct
        trim(cast(user_id as varchar)) as user_id,

        case
            when gender is null then 'unknown'

            when lower(trim(cast(gender as varchar))) in (
                'unknown',
                'unknownx',
                '?'
            ) then 'unknown'

            when lower(trim(cast(gender as varchar)))
                = 'prefer_not_to_say'
                then 'prefer_not_to_say'

            else lower(trim(cast(gender as varchar)))
        end as gender,

        case
            when country is null then 'unknown'

            when upper(trim(cast(country as varchar))) in (
                'XX',
                'ZZ'
            ) then 'unknown'

            else upper(trim(cast(country as varchar)))
        end as country,

        nullif(
            upper(trim(cast(campaign_id as varchar))),
            ''
        ) as campaign_id

    from source

),

resolved as (

    select
        user_id,

        case
            when count(
                distinct case
                    when gender <> 'unknown' then gender
                end
            ) = 1
            then max(
                case
                    when gender <> 'unknown' then gender
                end
            )

            else 'unknown'
        end as gender,

        case
            when count(distinct country) = 1
                then min(country)

            else 'unknown'
        end as country,

        case
            when count(distinct campaign_id) = 1
                then min(campaign_id)

            else null
        end as campaign_id,

        count(
            distinct case
                when gender <> 'unknown' then gender
            end
        ) > 1 as has_gender_conflict,

        count(distinct country) > 1
            as has_country_conflict,

        count(distinct campaign_id) > 1
            as has_campaign_conflict

    from normalized
    group by user_id

)

select *
from resolved