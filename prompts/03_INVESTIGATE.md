# Perform one bounded code/schema investigation

Inputs: one concrete question; selected evidence ids/line ranges; related requirement/decision/uncertainty ids.

Inspect only the declared scope. Do not run SQL, import/execute repository code, inspect secrets, or contact production. Identify observed implementation/schema facts separately from inferred implications. An absent symbol in this slice is not proof of absence across the system.

For a schema question, inspect each relevant field and constraint, including
qualifiers that appear only on a neighboring line. Check the requested properties
field by field before summarizing. The [worked examples](05_WORKED_EXAMPLES.md)
show how to distinguish a nullable definition from evidence about stored rows.
Keep examples separate from the current run's evidence.

Create an INV record with question, finite evidence-id scope, method, findings each with exact citations, nonempty limitations, and a specific next action. Include direct evidence for the main statement too. All citations must fall within the declared investigation scope.

For records 0.6, enumerate the final parent evidence followed by each finding's
evidence in order. Supply exactly one attribution entry per citation occurrence,
including repeated parent/finding quotes. Three parent citations plus three
one-citation findings need entries 0 through 5, not only 0 through 2. Describe the
finding each entry actually supports; distinguish zero-based citation indexes
from prose labels such as "finding 3". The worked examples show the complete map.

Make the key supported finding and its scope visible in the main statement;
do not hide an essential qualification only in nested findings. Distinguish a
constant declaration from the behavior of code that uses it: a duration constant
alone does not show that duration is enforced. A value used by a supplied check
is an implementation observation, not automatically a proposed product rule.
See the worked examples for both distinctions.

For a numeric check, state the input's meaning and the exact comparison. Distinguish
an existing count from the count after admitting one more item; describe the cases
immediately below and at a strict `<` boundary by reading the supplied text. Cite
both the constant value and the comparison. If a parent citation supplies the
constant while a narrower finding citation supplies only the comparison, say so
in their attribution reasons; do not claim the narrower span contains both.

Where a conclusion would require tests, runtime data, an inaccessible dependency, or a business decision, name the evidence needed rather than claiming completion. Link the investigation to the records it actually investigates. A proposed next test/query is not an executed result.
