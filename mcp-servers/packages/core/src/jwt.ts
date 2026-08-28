/**
 * Decodes (never verifies -- verification is Azure AD's job, we only read
 * claims for diagnostics) the payload of a JWT access token.
 */
export function decodeJwtPayload(token: string): Record<string, unknown> {
  const parts = token.split(".");
  if (parts.length < 2) {
    throw new Error("Not a JWT: expected at least 2 dot-separated segments.");
  }
  const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
  const padded = payload + "=".repeat((4 - (payload.length % 4)) % 4);
  const json = Buffer.from(padded, "base64").toString("utf8");
  return JSON.parse(json);
}
