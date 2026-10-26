SELECT game_id, side, schedule_pts, team_box_pts
FROM nba.box_reconciliation
WHERE team_box_differs AND NOT team_box_missing
