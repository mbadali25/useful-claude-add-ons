<!-- Moved verbatim from plugin/crew/README.md (12b. Optional: Perplexity MCP for web-grounded QA) by L-0726; the README keeps an index entry. -->

## 12b. Optional: Perplexity MCP for web-grounded QA

A code reviewer reads the diff. It cannot tell you that the API the diff calls
was deprecated four months ago, or that the dependency it adds has an open
advisory. The 0.20 `qa-researcher` specialist that did this second pass was
removed in crew 1.0 with the other specialists; `crew:researcher` answers the
same class of question from fetched sources (web tools and Context7), and a
Perplexity MCP server you configure yourself is one more source it can use.
