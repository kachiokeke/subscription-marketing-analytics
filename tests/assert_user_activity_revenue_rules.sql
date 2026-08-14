select *
from {{ ref('stg_user_activity') }}
where
    (
        event_type = 'sale'
        and (
            revenue_amount is null
            or revenue_amount <= 0
        )
    )
    or
    (
        event_type <> 'sale'
        and revenue_amount is not null
    )