select *
from {{ ref('mart_campaign_performance') }}
where
    attributed_users < trial_users

    or attributed_users < sale_users

    or sale_users < sale_without_trial_users

    or total_spend <= 0

    or initial_sale_revenue < 0

    or total_sale_revenue < initial_sale_revenue

    or trial_rate < 0
    or trial_rate > 1

    or sale_rate < 0
    or sale_rate > 1

    or (
        trial_users = 0
        and cost_per_trial is not null
    )

    or (
        trial_users > 0
        and (
            cost_per_trial is null
            or cost_per_trial <= 0
        )
    )

    or (
        sale_users = 0
        and cost_per_sale is not null
    )

    or (
        sale_users > 0
        and (
            cost_per_sale is null
            or cost_per_sale <= 0
        )
    )

    or initial_revenue_roas < 0

    or total_revenue_roas < initial_revenue_roas