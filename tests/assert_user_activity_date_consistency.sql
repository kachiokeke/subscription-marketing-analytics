select *
from {{ ref('stg_user_activity') }}
where
    source_date <> attribution_date

    or (
        event_type = 'start_onboarding'
        and cast(event_at as date) <> attribution_date
    )