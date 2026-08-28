#!/usr/bin/env node
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { runDoctor, printDoctorResult, buildAdminCredential, logToStderr } from "@badali404/mcp-ms-core";
import { createServer, delegatedScopes } from "./index.js";

async function main(): Promise<void> {
  const [subcommand] = process.argv.slice(2);

  if (subcommand === "doctor") {
    const credential = buildAdminCredential(delegatedScopes());
    const result = await runDoctor(
      credential,
      () => ({ authMode: credential.usedMode ?? "none (all methods failed)", tokenType: credential.usedTokenType ?? "app-only" }),
      delegatedScopes()
    );
    printDoctorResult("mcp-intune", result);
    process.exit(result.ok ? 0 : 1);
  }

  logToStderr("mcp-intune: starting stdio MCP server (app-only, tenant-wide device management)");
  const { server } = createServer();
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((err) => {
  process.stderr.write(`mcp-intune fatal error: ${err instanceof Error ? err.stack ?? err.message : String(err)}\n`);
  process.exit(1);
});
