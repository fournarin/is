# The plant's own data

Put the plant's files here. **Everything in this directory except this README
and `examples/` is ignored by git**, because plant data is under the same NDA as
the manuals and must not leave the machine it was copied to
([ADR-091](../docs/adr/0091-plant-data-arrives-as-csv.md)).

Four files, and none of them needs the others. Each is checked in full before
anything is used. An error names the file and line, and a file with one bad line
changes nothing. The vocabulary (machines, skills, shifts, PM tasks) is
`config/plant.yaml`. A name that file does not know is refused, not created.

`examples/` holds one valid file of each kind, matching the shipped
`config/plant.yaml`. A test reads them, so they stay valid.

## Signals - `signals.csv`

Machine readings, replayed through the rule engine and the trend extrapolator
exactly as the synthetic scenario is.

```
timestamp,machine_id,metric_name,value,unit
2026-03-02T06:00:00+07:00,MC-001,motor_temp_c,70.0,C
```

- `timestamp` must carry its UTC offset (`+07:00`). A time without one is
  refused rather than guessed. Rows may be in any order; they are sorted.
- `metric_name` must match a rule in `config/rules.yaml` for anything to fire.
- Exact duplicate rows, from overlapping exports, are read once.

Use it by setting, in `.env`:

```
SIGNAL_SOURCE=replay
SIGNAL_REPLAY_FILE=/app/plant-data/signals.csv
SIGNAL_SPEED=60        # 1 replays at the speed it was recorded
```

and restarting `worker-runtime`. The whole file is checked at boot, and the log
says how many readings, from when to when, for which machines.

## Technicians, roster and PM history

```
technicians.csv   user_id,display_name,skills,active
                  tech-a01,Anan P.,robot_mechanical;robot_controls,yes
roster.csv        date,shift_id,user_id,available_minutes
                  2026-10-01,morning,tech-a01,420
pm_history.csv    pm_task_ref,last_done
                  pm-mc-001-toothed-belt,2026-06-14
```

- `skills` are separated by `;` and must be listed under `skills:` in
  `plant.yaml`. `active` is `yes` or `no`, and defaults to `yes`.
- `available_minutes` is what that person can give to repair work on that shift,
  not the length of the shift. Leave out breaks, meetings and training.
- `last_done` is a date (midnight in the plant's time zone) or a time with an
  offset. It never moves a task's clock backwards. This is what stops every PM
  task starting overdue on installation day (ADR-083 §4).

Load them into the running stack:

```bash
docker compose -f docker-compose.yml -f docker-compose.rehearsal.yml --env-file .env \
  run --rm --no-deps rehearsal python scripts/import_plant_data.py \
  --technicians plant-data/technicians.csv \
  --roster plant-data/roster.csv \
  --pm-history plant-data/pm_history.csv
```

On a demo stack started by `scripts/rehearse.py`, which has no `.env`, use
`--env-file .env.example`. Without either, Compose stops at "POSTGRES_USER is
missing a value".

Running it again with the same files changes nothing. A technician with no
account gets one with a random password, printed once. Hand each person their
own.
