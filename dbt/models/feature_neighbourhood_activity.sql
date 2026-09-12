with joined as (
    select a.*, w.temperature, w.precipitation, w.wind, t.departures, e.event_intensity,
      extract(hour from timezone('America/Vancouver', timezone('UTC', a.timestamp))) as hour,
      extract(isodow from timezone('America/Vancouver', timezone('UTC', a.timestamp))) - 1 as weekday
    from raw_observed a
    join {{ ref('stg_weather') }} w using (timestamp)
    join {{ ref('stg_transit') }} t using (timestamp, neighbourhood)
    join {{ ref('stg_events') }} e using (timestamp, neighbourhood)
)
select *, lag(activity) over (partition by neighbourhood order by timestamp) as lag_1,
  lag(timestamp) over (partition by neighbourhood order by timestamp) as previous_timestamp,
  sin(2 * pi() * hour / 24) as hour_sin,
  cos(2 * pi() * hour / 24) as hour_cos,
  case when weekday >= 5 then 1 else 0 end as weekend
from joined
