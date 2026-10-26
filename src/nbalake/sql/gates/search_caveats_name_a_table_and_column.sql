SELECT c.table_name, c.column_name
FROM nba.caveats c
WHERE NOT EXISTS (
    SELECT 1 FROM duckdb_views() v
    WHERE v.database_name = 'lake' AND v.schema_name || '.' || v.view_name = c.table_name
)
AND NOT EXISTS (
    SELECT 1 FROM duckdb_tables() t
    WHERE t.database_name = 'lake' AND t.schema_name || '.' || t.table_name = c.table_name
      AND (c.column_name IS NULL OR EXISTS (
          SELECT 1 FROM duckdb_columns() k
          WHERE k.database_name = 'lake' AND k.schema_name = t.schema_name
            AND k.table_name = t.table_name AND k.column_name = c.column_name
      ))
)
