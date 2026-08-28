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
