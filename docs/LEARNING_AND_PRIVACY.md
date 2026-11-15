# Learning and privacy

nano Agent's learning features store bounded preferences and facts so behavior can adapt. This is structured memory and feedback, not automatic model-weight training. Inspect, correct, undo or delete learned items in the console. Learning can be turned off in settings.

The user model stores evidence and confidence rather than a full transcript. The project is designed not to retain chat text as a user profile. Chat history needed for the console may still exist in the local database; review the retention controls and protect the data directory. Backups also contain private assistant data.

Weekly review uses the configured model to suggest or apply only allowed preference changes. Lower-confidence changes are proposals. Changes that require code are ideas; code changes go through the separate patch proposal, test and owner-approval flow. Never enable a patch or skill without reviewing its effect.

Model providers receive prompts and context sent to them. With a hosted provider, that data leaves your machine according to that provider's terms. Choose a local provider if you require local inference. Optional Google and LINE connections also transmit data to those services. Disable integrations you do not use.

The project is early alpha. Verify actual retention and provider behavior for the version you install before using sensitive information.

## Review and control

Open **Settings → Learning** and **Settings → What I know about you** in the console to inspect learned items. Correct or remove anything inaccurate. **Settings → Appearance** offers Dark, Modern, Calm, and Minimal console themes; this preference affects presentation, not assistant permissions. `learning.enabled` can be set to false with `nano-agent config set learning.enabled false`. A disabled setting prevents new learning, but it does not delete existing local records; remove those separately if needed.

The console and database are local by default, yet hosted model calls still send the context needed for a response to the selected provider. LINE and Google features send data to those services when enabled. A local model endpoint reduces external model traffic, but it does not change what optional integrations transmit. Review provider terms and keep backups encrypted if they contain private conversations or facts.

Skills and web pages can contain instructions that conflict with your wishes. They are treated as untrusted input; outbound messages and code changes still require their approval flow. Review the pending action in the console before accepting it. See [SECURITY.md](../SECURITY.md) for the full boundary.

To check a preference change, reopen Settings and confirm the selected value remains after a reload. Learning's log records preference changes so you can review or undo them. If a setting looks wrong, restore its default in Settings → Learning; deleting a memory item is a separate action and does not follow from changing a theme.
