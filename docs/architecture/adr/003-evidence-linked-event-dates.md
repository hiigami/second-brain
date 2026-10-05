# ADR 003: Evidence-linked event dates in records 0.4

Status: accepted for the Patch H engine contract (2026-10-04). This is a software design decision, not approval of any source claim.

## Context

File `temporal.content_date` describes a document, while `manifest.created_at` describes capture. Neither proves when a business event occurred or when a requirement took effect. A document may describe several events, uncertain or conflicting dates, and future effective dates. Record-level metadata must preserve those distinctions without changing historical records or the frozen `project.json` v0.1 configuration.

## Decision

Records 0.4 retain records 0.3 segment-bound citations and coverage. Every record has an `events` array, which may be empty. Each event has a stable `EVT-...` id, a narrow statement, citation indexes into that record's exact frozen `evidence`, and an `event_date`; an `effective_date` is optional. Date expressions state `known`, `approximate`, `unknown`, or `conflicting`, with explicit basis and precision. Conflicting alternatives name their own citation indexes. Relative dates require a cited anchor value and a derivation note. Timestamp values carry timezone offsets; year/month/day values remain date precision rather than invented midnight instants. The checker validates syntax, reference integrity, range order, and consistent variants, but not semantic entailment. It does not derive event time from file names, message send time, capture time, or file modification time.

Re-anchoring preserves events only while all their cited support survives. It remaps citation indexes, reports dropped event ids, and marks the parent record degraded if support disappears. Older records 0.1–0.3 remain readable without event claims. Approved-release JSON preserves records 0.4 as-is; Patch I owns timeline views and chronology navigation.

## Consequences

Several events can share one document without forcing its content date onto each claim. Unknown and disputed dates remain explicit. Date-only and approximate intervals cannot be given a total business order by this contract; Patch I must show undated/overlapping groups honestly. Human semantic review is still required to check that a cited line actually supports the event, date, status, and authority. `project.json` v0.1, frozen runs, and prior releases are unchanged.
