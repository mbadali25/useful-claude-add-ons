#!/usr/bin/env node
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { runDoctor, printDoctorResult, getUserCredential, logToStderr } from "@mbadali/mcp-ms-core";
import { createServer, USER_SCOPES } from "./index.js";

async function main(): Promise<void> {
  const [subcommand] = process.argv.slice(2);

  if (subcommand === "doctor") {
    logToStderr("mcp-o365-user doctor: a device code prompt will appear below if you are not already signed in.");
    const credential = getUserCredential();
    const result = await runDoctor(credential, "delegated", USER_SCOPES);
    printDoctorResult("mcp-o365-user", result);
    process.exit(result.ok ? 0 : 1);
  }

  logToStderr("mcp-o365-user: starting stdio MCP server (delegated -- signed-in user's own data only)");
  const { server } = createServer();
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((err) => {
  process.stderr.write(`mcp-o365-user fatal error: ${err instanceof Error ? err.stack ?? err.message : String(err)}\n`);
  process.exit(1);
});
