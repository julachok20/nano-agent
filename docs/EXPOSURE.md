# Access and network exposure

The gateway binds to `127.0.0.1` by default. This keeps the web console local to the machine. Keep this setting when you only use the console on that machine.

For remote access, use a private network path such as Tailscale Serve or a VPN. Protect the machine account and the console token. If LINE needs to reach a webhook, expose only `/webhook/line` through an HTTPS reverse proxy; do not route the whole gateway to the public internet. Configure the proxy and firewall yourself, then verify routes from outside the machine.

The app can print examples for Tailscale, Cloudflare Tunnel or a custom domain. Those commands change your network exposure and should only be run after you understand who can reach the resulting URL. Funnel and quick tunnels can make an endpoint public.

Never expose the model server, Docker socket, SSH, database files, secrets file or unauthenticated admin endpoints. Use a firewall and restrict model endpoints to localhost or a trusted private network. Rotate any credential that may have been shared accidentally.
