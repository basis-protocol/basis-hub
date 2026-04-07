import { logger } from "./logger.js";

export async function sendAlert(message: string, error?: unknown): Promise<void> {
  const webhookUrl = process.env["SLACK_WEBHOOK_URL"] ?? process.env["DISCORD_WEBHOOK_URL"];

  const errorStr = error instanceof Error
    ? error.message
    : error != null
    ? String(error)
    : undefined;

  logger.error("ALERT: " + message, errorStr ? { error: errorStr } : undefined);

  if (!webhookUrl) return;

  try {
    const body = isDiscordWebhook(webhookUrl)
      ? JSON.stringify({
          content: `🚨 **Basis Keeper Alert**\n${message}${errorStr ? `\n\`\`\`${errorStr}\`\`\`` : ""}`,
        })
      : JSON.stringify({
          text: `🚨 *Basis Keeper Alert*\n${message}${errorStr ? `\n\`\`\`${errorStr}\`\`\`` : ""}`,
        });

    const res = await fetch(webhookUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });

    if (!res.ok) {
      logger.warn("Webhook delivery failed", { status: res.status });
    }
  } catch (err) {
    logger.warn("Failed to send webhook alert", {
      error: err instanceof Error ? err.message : String(err),
    });
  }
}

function isDiscordWebhook(url: string): boolean {
  return url.includes("discord.com");
}

export async function checkStaleness(
  oracle: { isStale: (token: string, maxAge: bigint) => Promise<boolean> },
  tokens: string[],
  maxAge: number
): Promise<void> {
  for (const token of tokens) {
    const stale = await oracle.isStale(token, BigInt(maxAge));
    if (stale) {
      await sendAlert(`STALE SCORE: ${token} not updated in ${maxAge}s`);
    }
  }
}
