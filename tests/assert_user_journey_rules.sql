select *
from {{ ref('fct_user_journey') }}
where
    trial_event_count not in (0, 1)

    or started_trial <> case
        when trial_at is not null then 1
        else 0
    end

    or made_sale <> case
        when first_sale_at is not null then 1
        else 0
    end

    or sale_without_trial <> case
        when first_sale_at is not null
         and trial_at is null then 1
        else 0
    end

    or has_multiple_sales <> case
        when sale_event_count > 1 then 1
        else 0
    end

    or (
        trial_at is not null
        and trial_at < onboarding_at
    )

    or (
        first_sale_at is not null
        and first_sale_at < onboarding_at
    )

    or (
        trial_at is not null
        and first_sale_at is not null
        and first_sale_at < trial_at
    )

    or (
        made_sale = 0
        and (
            sale_event_count <> 0
            or first_sale_at is not null
            or initial_sale_revenue is not null
            or total_sale_revenue <> 0
        )
    )

    or (
        made_sale = 1
        and (
            sale_event_count < 1
            or first_sale_at is null
            or initial_sale_revenue is null
            or initial_sale_revenue <= 0
            or total_sale_revenue < initial_sale_revenue
        )
    )