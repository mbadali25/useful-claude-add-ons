#!/usr/bin/env node
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { runDoctor, printDoctorResult, getAdminCredential, logToStderr } from "@mbadali/mcp-ms-core";
import { createServer } from "./index.js";

async function main(): Promise<void> {
  const [subcommand] = process.argv.slice(2);

  if (subcommand === "doctor") {
    const credential = getAdminCredential();
    const result = await runDoctor(credential, "app-only");
    printDoctorResult("mcp-msgraph", result);
    process.exit(result.ok ? 0 : 1);
  }

  logToStderr("mcp-msgraph: starting stdio MCP server (app-only, tenant directory data)");
  const { server } = createServer();
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((err) => {
  process.stderr.write(`mcp-msgraph fatal error: ${err instanceof Error ? err.stack ?? err.message : String(err)}\n`);
  process.exit(1);
});
