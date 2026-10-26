WITH stats AS (
    UNPIVOT (
        SELECT season, lg, bref_id, bref_team,
               mp::DOUBLE AS mp, trb::DOUBLE AS trb, orb::DOUBLE AS orb, drb::DOUBLE AS drb,
               stl::DOUBLE AS stl, blk::DOUBLE AS blk, tov::DOUBLE AS tov, gs::DOUBLE AS gs,
               x3p::DOUBLE AS x3p, x3pa::DOUBLE AS x3pa
        FROM nba.player_seasons
    )
    ON mp, trb, orb, drb, stl, blk, tov, gs, x3p, x3pa
    INTO NAME stat VALUE value
)
SELECT s.season, s.lg, s.bref_id, s.bref_team, s.stat, s.value, r.first_season
FROM stats s
JOIN nba.recorded_from r ON r.stat = s.stat AND r.lg = s.lg
WHERE r.first_season IS NULL OR s.season < r.first_season
