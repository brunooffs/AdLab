# Kibana Dashboard Setup

After the pipeline is running and data is flowing into Elasticsearch, follow
these steps to visualise your clickstream data in Kibana.

## 1. Open Kibana
Navigate to http://localhost:5601

## 2. Create Index Patterns
Go to **Stack Management → Index Patterns** and create patterns for:
- `clickstream_raw*`
- `clicks_per_page*`
- `clicks_per_country*`
- `clicks_per_device*`

Set `event_time` or `window_start` as the time field for each.

## 3. Suggested Visualisations

### Real-Time Event Rate (clickstream_raw)
- Type: **Line chart**
- X-axis: Date histogram on `event_time` (1 minute interval)
- Y-axis: Count

### Top Pages Bar Chart (clicks_per_page)
- Type: **Bar chart (horizontal)**
- X-axis: Sum of `event_count`
- Y-axis (buckets): Terms on `page`, top 10

### Events by Country (clicks_per_country)
- Type: **Choropleth Map** or **Pie chart**
- Buckets: Terms on `country`
- Metric: Sum of `event_count`

### Device Breakdown (clicks_per_device)
- Type: **Donut chart**
- Buckets: Terms on `device`
- Metric: Sum of `event_count`

### Action Type Heatmap (clickstream_raw)
- Type: **Heat map**
- X-axis: Date histogram on `event_time`
- Y-axis: Terms on `action`
- Value: Count

## 4. Build a Dashboard
Combine the above into a single Kibana Dashboard named
**"Clickstream Overview"** for a live pipeline monitoring view.
