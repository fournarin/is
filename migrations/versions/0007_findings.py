"""Findings, and the partial unique index that is invariant 8.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-13

The lifecycle of ADR-023 as a table. The column list follows `Finding` in
`contracts/work.py`; the two things worth reading are the index and the CHECKs.

**The partial unique index is the alarm flood defence made structural.** ADR-023
says a repeat firing updates the existing record while an open or acknowledged
one exists for (machine_id, rule_id). The service does that in one UPDATE, and
this index is what makes a second record impossible if the service is ever wrong:
one overheating motor becoming a hundred work orders is how the system destroys
itself in its first hour on real data, and that is too expensive to leave to a
query being written correctly every time.

No column has `DEFAULT now()`, for the reason recorded in 0001 (ADR-028).
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE finding_number")

    op.execute("""
        CREATE TABLE finding (
            finding_ref     text PRIMARY KEY
                            DEFAULT 'F-' || lpad(nextval('finding_number')::text, 6, '0'),

            machine_id      text NOT NULL CHECK (length(machine_id) > 0),
            -- Declared by the rule, never inferred from the signal. A rule that
            -- cannot say which part it watches uses 'unknown', and layer 2 then
            -- serves a fault-finding playbook rather than a repair one
            -- (ADR-009, ADR-016).
            component       text NOT NULL CHECK (length(component) > 0),
            symptom_code    text NOT NULL CHECK (length(symptom_code) > 0),
            severity        text NOT NULL
                            CHECK (severity IN ('low', 'medium', 'high', 'critical')),
            rule_id         text NOT NULL CHECK (length(rule_id) > 0),
            detected_at     timestamptz NOT NULL,

            -- Which value, how far past the threshold, for how long. Without it
            -- the alert cannot be explained to a technician, and an alert that
            -- cannot be explained gets ignored (principle 3, ADR-042).
            evidence        jsonb NOT NULL,

            kind            text NOT NULL DEFAULT 'detected'
                            CHECK (kind IN ('detected', 'predicted')),
            eta             timestamptz,
            eta_confidence  interval,

            status          text NOT NULL DEFAULT 'open'
                            CHECK (status IN ('open', 'acknowledged', 'resolved',
                                              'expired', 'superseded')),
            occurrence_count integer NOT NULL DEFAULT 1 CHECK (occurrence_count >= 1),
            last_seen_at    timestamptz,
            superseded_by   text REFERENCES finding (finding_ref),

            resolved_at     timestamptz,

            -- A predicted Finding without both is an opinion presented as a
            -- forecast. The contract refuses one without the other and so does
            -- the table, because a row can be written by something that is not
            -- the contract (ADR-020, ui.md 2.2).
            CONSTRAINT a_prediction_carries_its_interval CHECK (
                kind <> 'predicted' OR (eta IS NOT NULL AND eta_confidence IS NOT NULL)
            ),
            -- A detected Finding has already crossed the threshold; an eta on it
            -- would be a forecast of something that has happened.
            CONSTRAINT a_detection_has_no_eta CHECK (kind <> 'detected' OR eta IS NULL),
            CONSTRAINT a_superseded_finding_names_its_successor CHECK (
                status <> 'superseded' OR superseded_by IS NOT NULL
            ),
            CONSTRAINT a_resolved_finding_has_a_time CHECK (
                status <> 'resolved' OR resolved_at IS NOT NULL
            )
        )
    """)

    # Invariant 8, structurally. While one is open or acknowledged for this
    # (machine, rule), a second cannot be written at all - by this service, by a
    # script, or by two workers evaluating the same signal at the same moment.
    op.execute("""
        CREATE UNIQUE INDEX one_live_finding_per_machine_and_rule
        ON finding (machine_id, rule_id)
        WHERE status IN ('open', 'acknowledged')
    """)

    # The cooldown lookup: when was this pair last resolved (ADR-023 section 3).
    op.execute("""
        CREATE INDEX finding_recently_resolved_idx
        ON finding (machine_id, rule_id, resolved_at DESC)
        WHERE status = 'resolved'
    """)

    # Supersession looks for an open prediction on the same machine and
    # component (ADR-023 section 7), which is also where the ETA error of that
    # prediction becomes known.
    op.execute("""
        CREATE INDEX finding_open_predictions_idx
        ON finding (machine_id, component)
        WHERE kind = 'predicted' AND status IN ('open', 'acknowledged')
    """)


def downgrade() -> None:
    """Not supported (ADR-031). The table is the record of what the plant did and
    when the system noticed."""
    raise NotImplementedError("downgrade is not supported (ADR-031)")
