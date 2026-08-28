/**
 * Every write/destructive tool in every server must call this before doing
 * anything. It requires BOTH the env flag (an operator decision made once,
 * outside any one conversation) AND the per-call confirm:true parameter (a
 * model/user decision made for this specific action). Neither alone is
 * enough.
 */
export class WriteNotAllowedError extends Error {
  constructor(toolName: string, reason: string) {
    super(`Tool "${toolName}" is a write/destructive tool and was blocked: ${reason}`);
    this.name = "WriteNotAllowedError";
  }
}

export interface WriteGateArgs {
  confirm?: boolean;
}

export function assertWriteAllowed(toolName: string, args: WriteGateArgs): void {
  if (process.env.MCP_MS_ALLOW_WRITES !== "1") {
    throw new WriteNotAllowedError(
      toolName,
      "MCP_MS_ALLOW_WRITES is not set to \"1\". Set it in the environment that launches this server to enable writes."
    );
  }
  if (args.confirm !== true) {
    throw new WriteNotAllowedError(
      toolName,
      "the call did not pass confirm: true. Re-issue the call with confirm: true to proceed."
    );
  }
}
