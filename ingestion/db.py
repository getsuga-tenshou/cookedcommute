"""Deprecated. The Postgres serving layer was replaced by Snowflake in the ELT
migration. Raw landing now goes through `ingestion.sinks` (lake/ADLS) and is
loaded into Snowflake by `ingestion.warehouse` / the scheduled COPY task.

Kept only as a breadcrumb; safe to delete.
"""
