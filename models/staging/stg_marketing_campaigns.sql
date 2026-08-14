with source as (

    select *
    from {{ source('raw', 'marketing_campaigns') }}

),

cleaned as (

    select
        upper(trim(cast(campaign_id as varchar))) as campaign_id,
        trim(cast(campaign_name as varchar)) as campaign_name,
        trim(cast(campaign_type as varchar)) as campaign_type

    from source

)

select *
from cleaned