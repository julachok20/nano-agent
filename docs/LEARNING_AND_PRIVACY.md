# Learning and privacy

nano Agent's learning features store bounded preferences and facts so behavior can adapt. This is structured memory and feedback, not automatic model-weight training. Inspect, correct, undo or delete learned items in the console. Learning can be turned off in settings.

The user model stores evidence and confidence rather than a full transcript. The project is designed not to retain chat text as a user profile. Chat history needed for the console may still exist in the local database; review the retention controls and protect the data directory. Backups also contain private assistant data.

Weekly review uses the configured model to suggest or apply only allowed preference changes. Lower-confidence changes are proposals. Changes that require code are ideas; code changes go through the separate patch proposal, test and owner-approval flow. Never enable a patch or skill without reviewing its effect.

Model providers receive prompts and context sent to them. With a hosted provider, that data leaves your machine according to that provider's terms. Choose a local provider if you require local inference. Optional Google and LINE connections also transmit data to those services. Disable integrations you do not use.

The project is early alpha. Verify actual retention and provider behavior for the version you install before using sensitive information.
