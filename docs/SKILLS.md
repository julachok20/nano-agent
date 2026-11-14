# Skills

Skills are instruction folders that extend the agent's knowledge of a task. nano Agent keeps imported skills in a pending area until the owner reviews and enables them. Review a skill's source before enabling it; skill text can influence the model but does not grant new tools or bypass the tool permission checks.

Manage skills in the console or with `nano-agent skills list`, `nano-agent skills add` and `nano-agent skills enable`. Check `nano-agent skills --help` for command details. Keep imported folders small, readable and free of secrets. Remove skills you no longer trust.

The format follows the common `SKILL.md` convention. A skill should state its purpose, when to use it, and clear steps. Do not treat downloaded skill instructions as trusted code.
