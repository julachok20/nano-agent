# Optional LINE setup

The connector uses the official LINE Messaging API. Create a LINE Messaging API channel in LINE Developers, set its webhook URL to the public HTTPS URL ending in `/webhook/line`, and copy its channel secret and access token into the setup flow. Configure the same webhook URL in LINE Developers and enable webhooks there. LINE's signature is checked before an event is accepted.

Pair the owner from the console or with `nano-agent line pair`, then check `nano-agent line status`. Use the webhook verify function in LINE Developers after the endpoint is reachable. Do not test with real contacts; use your own test account and test chat.

External access is required for LINE to reach the webhook. Keep the console private and expose only the webhook path through a carefully configured HTTPS proxy. Consult [EXPOSURE.md](EXPOSURE.md) and [SECURITY.md](../SECURITY.md). Do not expose the local console, database, model server or admin routes publicly.

The LINE connector and delivery path have not been verified against a live account by the repository's fake-provider checks. Personal LINE browser automation is not part of this project.
