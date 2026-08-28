/**
 * Minimal shape-compatible with the SDK's CallToolResult. Defined locally so
 * this package does not need to depend on @modelcontextprotocol/sdk just for
 * a type.
 */
export interface ToolResult {
  [key: string]: unknown;
  content: Array<{ type: "text"; text: string }>;
  isError?: boolean;
}

export function textResult(data: unknown): ToolResult {
  const text = typeof data === "string" ? data : JSON.stringify(data, null, 2);
  return { content: [{ type: "text", text }] };
}

/** Renders a GraphClient.getAllPages() result. The items are the primary JSON
 * payload (unchanged shape from before pagination reported truncation); when
 * the page cap was hit, appends a plain-text note so the model doesn't present
 * a partial result as if it were the whole answer. */
export function pagedResult<T>(page: { items: T[]; truncated: boolean }): ToolResult {
  const result = textResult(page.items);
  if (page.truncated) {
    result.content.push({
      type: "text",
      text:
        "Note: this result was truncated at the page cap -- more data may exist on the " +
        "server than is shown above. Narrow the query (e.g. add a $filter) or tell the " +
        "user the list may be incomplete.",
    });
  }
  return result;
}

export function errorResult(err: unknown): ToolResult {
  const message = err instanceof Error ? err.message : String(err);
  return { content: [{ type: "text", text: `Error: ${message}` }], isError: true };
}

/** Wraps a tool handler so any thrown error becomes a proper MCP error result
 * instead of crashing the server process. */
export function withToolErrorHandling<Args, R = ToolResult>(
  fn: (args: Args) => Promise<R>
): (args: Args) => Promise<R | ToolResult> {
  return async (args: Args) => {
    try {
      return await fn(args);
    } catch (err) {
      return errorResult(err);
    }
  };
}
