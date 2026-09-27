# ADR-091: Plant data arrives as CSV

Written on 2026-09-27. Builds the second of
[ADR-002](0002-signalsource-interface-with-three-implementations.md)'s three
sources. Revisits [ADR-078](0078-a-demo-roster-is-a-separate-script.md), which
said the plant's own roster would replace the demo's without saying how, and
[ADR-083](0083-the-pm-schedule-becomes-a-source-of-work.md) §4 and #118, where
every PM task starts overdue because nothing can load when it was last done.
[ADR-086](0086-what-this-term-does-not-do.md) closed #118 until the maintenance
history arrived. This record builds the way in, so the history can be loaded
the day it does arrive.

## Context

The advisor sees the system as something for real use, and has said two things
about data: that plant sensor data is "still far off", and that technician
data (names, skills, shifts) "can probably be obtained". Until now the system
had no way to take in either. `SIGNAL_SOURCE=replay` refused at boot as "not
built yet", and the only thing that could write a technician row was
`seed_demo_roster.py`, which invents three people on purpose.

So if the plant sent a spreadsheet tomorrow, nobody could use it without
writing code. That is the gap between a working demo and a system that can be
installed.

## Decision

1. **`ReplaySource` reads the `Signal` contract as CSV**
   (`timestamp,machine_id,metric_name,value,unit`, with the columns in any
   order). `SIGNAL_SOURCE=replay` and `SIGNAL_REPLAY_FILE` select it. The file
   is read and checked in full at boot.
2. **`scripts/import_plant_data.py` reads three CSVs**, each optional:
   technicians with their skills, the roster by date and shift with available
   minutes, and the last-done date of each PM task.
3. **All-or-nothing, and every bad line named.** One transaction writes
   everything, after every row of every file has been checked. The error lists
   each problem as `file:line`, up to twenty, so an export is fixed in one pass.
4. **`config/plant.yaml` is the vocabulary.** A skill, shift, PM task or column
   it does not know is refused, never created (ADR-027).
5. **Times are never guessed.** A signal timestamp or a PM time without a UTC
   offset is refused. A PM date with no time is midnight in the plant's
   configured zone, which is a stated fact and not a guess (ADR-028).
6. **Plant files live in `plant-data/`**, which git ignores apart from its README
   and `examples/`. It is mounted read-only into `worker-runtime`.

## Reasons

- **CSV is what arrives first.** A historian export, a CMMS report and a shift
  spreadsheet all become CSV without anybody on the plant side writing code.
  OPC UA needs a network route and an IT ticket. ADR-082 records that neither
  is coming this term.
- **Replay gives real data the same path as synthetic data.** The rule engine,
  the trend extrapolator and the feed pacing all run unchanged. The first real
  export therefore tests the system rather than an adapter.
- **Out-of-order rows are sorted, not refused.** Exports are often grouped by
  tag. The ordering can be recovered, and the port's promise (time never goes
  backwards) holds after sorting.
- **An exact duplicate is dropped, but two different values at one instant are
  kept.** Overlapping exports repeat rows. Two values that disagree are the
  data saying something, and the rule engine is where that gets judged.

## What it costs, and what it does not do

- **A replay file is read into memory at boot.** A month of one-minute readings
  from twenty tags is under a million rows, which is fine. A year of one-second
  data is not, and the reader would then need to stream from a sorted file.
- **No `ground_truth()`.** Replay can detect and predict, but it cannot measure
  ETA error. That needs the failure times, which are in the maintenance history
  (ADR-082) and not in a signal file.
- **Accounts get random passwords, printed once.** That is weaker than the
  plant's own identity system, and ADR-036's adapter is where that system
  plugs in.
- **`live` (OPC UA) is still not built,** and still refuses at boot by name.

## Consequences

- `README.md`'s "only one of the three signal sources is built" becomes two of
  three, and "every PM task starts overdue" gains a remedy.
- `plant-data/examples/` is kept valid by a test against the shipped
  `config/plant.yaml`, including one test that its signals cross a rule for
  long enough to fire.
- #118 can close. What it waited for was a way to load the dates, and that way
  now exists. The dates themselves still have to come from the plant.
