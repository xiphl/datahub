---
title: "Deployment Environment Variables"
---

# Environment Variables

The following is a summary of a few important environment variables which expose various levers which control how
DataHub works.

## Feature Flags

| Variable                                          | Default | Unit/Type | Components                              | Description                                                                                                                 |
|---------------------------------------------------|---------|-----------|-----------------------------------------|-----------------------------------------------------------------------------------------------------------------------------|
| `UI_INGESTION_ENABLED`                            | `true`  | boolean   | [`GMS`, `MCE Consumer`]                 | Enable UI based ingestion.                                                                                                  |
| `DATAHUB_ANALYTICS_ENABLED`                       | `true`  | boolean   | [`Frontend`, `GMS`]                     | Enabled analytics within DataHub.                                                                                           |
| `BOOTSTRAP_SYSTEM_UPDATE_WAIT_FOR_SYSTEM_UPDATE`  | `true`  | boolean   | [`GMS`, `MCE Consumer`, `MAE Consumer`] | Do not wait for the `system-update` to complete before starting. This should typically only be disabled during development. |

## Ingestion

| Variable                           | Default | Unit/Type | Components              | Description                                                                                                                                                                       |
|------------------------------------|---------|-----------|-------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `ASYNC_INGESTION_DEFAULT`          | `false` | boolean   | [`GMS`]                 | Asynchronously process ingestProposals by writing the ingestion MCP to Kafka. Typically enabled with standalone consumers.                                                        |
| `MCP_CONSUMER_ENABLED`             | `true`  | boolean   | [`GMS`, `MCE Consumer`] | When running in standalone mode, disabled on `GMS` and enabled on separate `MCE Consumer`.                                                                                        |
| `MCL_CONSUMER_ENABLED`             | `true`  | boolean   | [`GMS`, `MAE Consumer`] | When running in standalone mode, disabled on `GMS` and enabled on separate `MAE Consumer`.                                                                                        |
| `PE_CONSUMER_ENABLED`              | `true`  | boolean   | [`GMS`, `MAE Consumer`] | When running in standalone mode, disabled on `GMS` and enabled on separate `MAE Consumer`.                                                                                        |
| `ES_BULK_REQUESTS_LIMIT`           | 1000    | docs      | [`GMS`, `MAE Consumer`] | Number of bulk documents to index. `MAE Consumer` if standalone.                                                                                                                  |
| `ES_BULK_FLUSH_PERIOD`             | 1       | seconds   | [`GMS`, `MAE Consumer`] | How frequently indexed documents are made available for query.                                                                                                                    |
| `ALWAYS_EMIT_CHANGE_LOG`           | `false` | boolean   | [`GMS`]                 | Enables always emitting a MCL even when no changes are detected. Used for Time Based Lineage when no changes occur.                                                               |                                                                                                                  |
| `GRAPH_SERVICE_DIFF_MODE_ENABLED`  | `true`  | boolean   | [`GMS`]                 | Enables diff mode for graph writes, uses a different code path that produces a diff from previous to next to write relationships instead of wholesale deleting edges and reading. |

## Caching

| Variable                                   | Default  | Unit/Type | Components | Description                                                                          |
|--------------------------------------------|----------|-----------|------------|--------------------------------------------------------------------------------------|
| `SEARCH_SERVICE_ENABLE_CACHE`              | `false`  | boolean   | [`GMS`]    | Enable caching of search results.                                                    |
| `SEARCH_SERVICE_CACHE_IMPLEMENTATION`      | caffeine | string    | [`GMS`]    | Set to `hazelcast` if the number of GMS replicas > 1 for enabling distributed cache. |
| `CACHE_TTL_SECONDS`                        | 600      | seconds   | [`GMS`]    | Default cache time to live.                                                          |
| `CACHE_MAX_SIZE`                           | 10000    | objects   | [`GMS`]    | Maximum number of items to cache.                                                    |
| `LINEAGE_SEARCH_CACHE_ENABLED`             | `true`   | boolean   | [`GMS`]    | Enables in-memory cache for searchAcrossLineage query.                               |
| `CACHE_ENTITY_COUNTS_TTL_SECONDS`          | 600      | seconds   | [`GMS`]    | Homepage entity count time to live.                                                  |
| `CACHE_SEARCH_LINEAGE_TTL_SECONDS`         | 86400    | seconds   | [`GMS`]    | Search lineage cache time to live.                                                   |
| `CACHE_SEARCH_LINEAGE_LIGHTNING_THRESHOLD` | 300      | objects   | [`GMS`]    | Lineage graphs exceeding this limit will use a local cache.                          |

## Search

| Variable                                            | Default                | Unit/Type | Components                                                      | Description                                                              |
|-----------------------------------------------------|------------------------|-----------|-----------------------------------------------------------------|--------------------------------------------------------------------------|
| `INDEX_PREFIX`                                      | ``                     | string    | [`GMS`, `MAE Consumer`, `Elasticsearch Setup`, `System Update`] | Prefix Elasticsearch indices with the given string.                      |
| `ELASTICSEARCH_NUM_SHARDS_PER_INDEX`                | 1                      | integer   | [`System Update`]                                               | Default number of shards per Elasticsearch index.                        |
| `ELASTICSEARCH_NUM_REPLICAS_PER_INDEX`              | 1                      | integer   | [`System Update`]                                               | Default number of replica per Elasticsearch index.                       |
| `ELASTICSEARCH_BUILD_INDICES_RETENTION_VALUE`       | 60                     | integer   | [`System Update`]                                               | Number of units for the retention of Elasticsearch clone/backup indices. |
| `ELASTICSEARCH_BUILD_INDICES_RETENTION_UNIT`        | DAYS                   | string    | [`System Update`]                                               | Unit for the retention of Elasticsearch clone/backup indices.            |
| `ELASTICSEARCH_QUERY_EXACT_MATCH_EXCLUSIVE`         | `false`                | boolean   | [`GMS`]                                                         | Only return exact matches when using quotes.                             |
| `ELASTICSEARCH_QUERY_EXACT_MATCH_WITH_PREFIX`       | `true`                 | boolean   | [`GMS`]                                                         | Include prefix match in exact match results.                             |
| `ELASTICSEARCH_QUERY_EXACT_MATCH_FACTOR`            | 10.0                   | float     | [`GMS`]                                                         | Multiply by this number on true exact match.                             |
| `ELASTICSEARCH_QUERY_EXACT_MATCH_PREFIX_FACTOR`     | 1.6                    | float     | [`GMS`]                                                         | Multiply by this number when prefix match.                               |
| `ELASTICSEARCH_QUERY_EXACT_MATCH_CASE_FACTOR`       | 0.7                    | float     | [`GMS`]                                                         | Multiply by this number when case insensitive match.                     |
| `ELASTICSEARCH_QUERY_EXACT_MATCH_ENABLE_STRUCTURED` | `true`                 | boolean   | [`GMS`]                                                         | When using structured query, also include exact matches.                 |
| `ELASTICSEARCH_QUERY_PARTIAL_URN_FACTOR`            | 0.5                    | float     | [`GMS`]                                                         | Multiply by this number when partial token match on URN)                 |
| `ELASTICSEARCH_QUERY_PARTIAL_FACTOR`                | 0.4                    | float     | [`GMS`]                                                         | Multiply by this number when partial token match on non-URN field.       |
| `ELASTICSEARCH_QUERY_CUSTOM_CONFIG_ENABLED`         | `false`                | boolean   | [`GMS`]                                                         | Enable search query and ranking customization configuration.             |
| `ELASTICSEARCH_QUERY_CUSTOM_CONFIG_FILE`            | `search_config.yml`    | string    | [`GMS`]                                                         | The location of the search customization configuration.                  |

## Kafka

In general, there are **lots** of Kafka configuration environment variables for both the producer and consumers defined in the official Spring Kafka documentation [here](https://docs.spring.io/spring-boot/docs/2.7.10/reference/html/application-properties.html#appendix.application-properties.integration).
These environment variables follow the standard Spring representation of properties as environment variables.
Simply replace the dot, `.`, with an underscore, `_`, and convert to uppercase.

| Variable                                             | Default  | Unit/Type | Components                               | Description                                                                                      |
|------------------------------------------------------|----------|-----------|------------------------------------------|--------------------------------------------------------------------------------------------------|
| `KAFKA_LISTENER_CONCURRENCY`                         | 1        | integer   | [`GMS`, `MCE Consumer`, `MAE Consumer`]  | Number of Kafka consumer threads. Optimize throughput by matching to topic partitions.           |
| `SPRING_KAFKA_PRODUCER_PROPERTIES_MAX_REQUEST_SIZE`  | 1048576  | bytes     | [`GMS`, `MCE Consumer`, `MAE Consumer`]  | Max produced message size. Note that the topic configuration is not controlled by this variable. |
