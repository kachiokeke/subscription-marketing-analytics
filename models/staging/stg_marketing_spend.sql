-- Example staging model, provided to show the pattern.
-- Build the other staging models (stg_marketing_campaigns, stg_dim_user, stg_user_activity)
-- following the same shape: one source, cleaned, ready for downstream joins.

with source as (
    select * from {{ source('raw', 'marketing_spend') }}
),

renamed as (
    select
        cast(date as date) as spend_date,
        cast(campaign_id as varchar) as campaign_id,
        cast(spend as double) as spend_amount
    from source
)

select * from renamed
