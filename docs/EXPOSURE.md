# Access and network exposure

The gateway binds to `127.0.0.1` by default. This keeps the web console local to the machine. Keep this setting when you only use the console on that machine.

For remote access, use a private network path such as Tailscale Serve or a VPN. Protect the machine account and the console token. If LINE needs to reach a webhook, expose only `/webhook/line` through an HTTPS reverse proxy; do not route the whole gateway to the public internet. Configure the proxy and firewall yourself, then verify routes from outside the machine.

The app can print examples for Tailscale, Cloudflare Tunnel or a custom domain. Those commands change your network exposure and should only be run after you understand who can reach the resulting URL. Funnel and quick tunnels can make an endpoint public.

Never expose the model server, Docker socket, SSH, database files, secrets file or unauthenticated admin endpoints. Use a firewall and restrict model endpoints to localhost or a trusted private network. Rotate any credential that may have been shared accidentally.

## Choose an access path

| Need | Suggested path | Reachability |
| --- | --- | --- |
| Console on this computer | Keep `gateway.host = "127.0.0.1"` | Local only |
| Console from your own devices | Tailscale Serve or a private VPN | Members of your private network |
| LINE webhook | HTTPS reverse proxy for `/webhook/line` only | Public to LINE |
| Your own domain | TLS reverse proxy with route restrictions | Depends on your proxy rules |

Cloudflare Tunnel can provide a public HTTPS URL for the webhook without opening an inbound port, but a tunnel that forwards the whole gateway also exposes console routes. Configure the tunnel or an edge proxy to allow only the webhook path. Tailscale Funnel is public; Tailscale Serve stays on your tailnet. Test from a device outside your local network and confirm both that LINE can reach `/webhook/line` and that unrelated routes are refused.

The gateway's `gateway.public_url` is the address users and LINE see; `gateway.host` is the local bind address. Keep the bind on loopback when a same-machine proxy or tunnel forwards to it. Preserve HTTPS through the public edge and protect the owner console token as a password. Avoid posting token-bearing console URLs or proxy logs.

## Verify route boundaries

After configuring a proxy, request `/healthz` from the intended network and confirm it responds. From an unauthenticated browser, an `/api/me` request must return 401; the public console HTML shell contains no owner data until login. A public LINE edge should forward `/webhook/line` only and reject `/api/me`, `/console`, and `/static/` routes. If a route is reachable from a network where it should not be, close the proxy route first, then check its path rules and firewall.
