select * from {{ ref('feature_neighbourhood_activity') }} where activity < 0 or activity > 100
