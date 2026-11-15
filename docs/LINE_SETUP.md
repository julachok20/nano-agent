# Optional LINE setup

The connector uses the official LINE Messaging API. Create a LINE Messaging API channel in LINE Developers, set its webhook URL to the public HTTPS URL ending in `/webhook/line`, and copy its channel secret and access token into the setup flow. Configure the same webhook URL in LINE Developers and enable webhooks there. LINE's signature is checked before an event is accepted.

Pair the owner from the console or with `nano-agent line pair`, then check `nano-agent line status`. Use the webhook verify function in LINE Developers after the endpoint is reachable. Do not test with real contacts; use your own test account and test chat.

External access is required for LINE to reach the webhook. Keep the console private and expose only the webhook path through a carefully configured HTTPS proxy. Consult [EXPOSURE.md](EXPOSURE.md) and [SECURITY.md](../SECURITY.md). Do not expose the local console, database, model server or admin routes publicly.

The LINE connector and delivery path have not been verified against a live account by the repository's fake-provider checks. Personal LINE browser automation is not part of this project.

## LINE Developers checklist

1. Open [LINE Developers Console](https://developers.line.biz/console/) and sign in.
2. Create a Provider, then create a **Messaging API** channel for the bot.
3. In **Basic settings**, copy the **Channel secret**.
4. In **Messaging API**, issue a **Channel access token (long-lived)** and copy it.
5. In LINE Official Account Manager, turn off **Auto-reply messages** and **Greeting messages** so they do not compete with the agent.
6. Configure a public HTTPS endpoint that forwards **only** `/webhook/line` to the local gateway. Paste `https://YOUR-PUBLIC-URL/webhook/line` into **Webhook URL** in LINE Developers, press **Verify**, then enable **Use webhook**.
7. Run `nano-agent line setup` and enter the secret and token through its hidden prompts. Run `nano-agent line pair` with your own account, then `nano-agent line status`.

The same web checklist is available locally with `nano-agent line guide`. Keep the long-lived access token and channel secret out of Git and screenshots. If Verify fails, confirm the public DNS and TLS certificate, the exact `/webhook/line` path, and that the gateway is running. A failed signature check means the secret does not match the channel or the request was altered.

Optional LIFF access is separate: create a LINE Login channel, add a LIFF app with endpoint `https://YOUR-PUBLIC-URL/console` and `openid` scope, then copy the LIFF ID. Only do this if you intentionally expose a protected console path; the default local console cannot be opened from LINE on another device.

## Check the connection

Run `nano-agent line status` after setup. It should report the channel configuration and whether an owner is paired; a configured channel alone does not prove the webhook is reachable. Use LINE Developers' **Verify** action for the webhook, then test only with a dedicated test account and chat, never real contacts. The repository's fake LINE tests check signatures and routing but do not verify delivery in a real LINE account. If pairing or delivery fails, inspect `nano-agent logs --follow` with tokens redacted and confirm the exact public webhook URL, channel secret, and owner pairing.
