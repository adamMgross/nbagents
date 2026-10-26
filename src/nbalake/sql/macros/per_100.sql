-- A rate per 100 possessions, NULL when possessions is zero.
-- example: select per_100(112, 98)
CREATE OR REPLACE TEMP MACRO per_100(points, possessions) AS
    100.0 * points / nullif(possessions, 0);
