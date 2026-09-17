# TMDL syntax reference

TMDL is indentation-based, similar to YAML. Source: Microsoft Learn, TMDL overview and how-to pages.

**Object declaration:** `<object type> <object name>` on its own line, e.g. `table Sales`, `column 'Customer Key'`, `measure Sales`. Object name is bare if it contains no spaces/special characters, single-quoted otherwise.

**Properties:** `<property>: <value>` (colon) for simple properties, e.g. `dataType: int64`, `formatString: $ #,##0`. Nesting is expressed purely through indentation - a property or child object belongs to whichever object header is the nearest less-indented line above it.

**Expressions (text properties):** use `=` (equals), not colon - e.g. `measure Sales = SUM(...)`, `source = let ... in ...`. Two forms:
- **Inline:** value follows `=` directly on the same line - used when the expression is a single line.
- **Multi-line:** value starts on the line immediately following the property/object declaration line, wrapped so the whole block is treated as one value.

**Expression values are read verbatim.** Expressions (DAX/M) can contain characters that would otherwise look like TMDL syntax (quotes, brackets, colons, indentation-like whitespace), so the parser treats the text of an expression as opaque: everything up to its closing boundary is copied as-is after dedenting and is not parsed as nested structure.

**Indentation is the only nesting signal.** There is no explicit end-of-block marker (no closing brace) - a line's membership in a parent's children is determined solely by its indentation being deeper than the parent header's indentation. A line at the same or shallower indentation ends the current block.
