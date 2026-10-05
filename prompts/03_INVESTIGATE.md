# Perform one bounded code/schema investigation

Inputs: one concrete question; selected evidence ids/line ranges; related requirement/decision/uncertainty ids.

Inspect only the declared scope. Do not run SQL, import/execute repository code, inspect secrets, or contact production. Identify observed implementation/schema facts separately from inferred implications. An absent symbol in this slice is not proof of absence across the system.

Create an INV record with question, finite evidence-id scope, method, findings each with exact citations, nonempty limitations, and a specific next action. Include direct evidence for the main statement too. All citations must fall within the declared investigation scope.

Where a conclusion would require tests, runtime data, an inaccessible dependency, or a business decision, name the evidence needed rather than claiming completion. Link the investigation to the records it actually investigates. A proposed next test/query is not an executed result.
