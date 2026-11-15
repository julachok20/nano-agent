# Skills

Skills are instruction folders that extend the agent's knowledge of a task. nano Agent keeps imported skills in a pending area until the owner reviews and enables them. Review a skill's source before enabling it; skill text can influence the model but does not grant new tools or bypass the tool permission checks.

Manage skills in the console or with `nano-agent skills list`, `nano-agent skills add` and `nano-agent skills enable`. Check `nano-agent skills --help` for command details. Keep imported folders small, readable and free of secrets. Remove skills you no longer trust.

The format follows the common `SKILL.md` convention. A skill should state its purpose, when to use it, and clear steps. Do not treat downloaded skill instructions as trusted code.

## Import and review

```bash
nano-agent skills add /path/to/skill-folder
nano-agent skills list
nano-agent skills enable skill-name
```

`skills add` also accepts a zip, a single `SKILL.md`, a GitHub URL or `-` for stdin. An import stays disabled until the owner enables it. Open the imported `SKILL.md` and any files it references; check for requests to reveal credentials, run shell commands, send data elsewhere or weaken approvals. Only then enable it. The console shows pending and enabled skills too.

A simple skill folder contains a `SKILL.md` with a title, a short description of when to apply it, and steps that can be followed without hidden dependencies. Keep credentials in the app's secret store, never inside skill files. Disabling or deleting a skill stops future use of its instructions but does not erase any output it already produced.

After import, `nano-agent skills list` should show the new skill as pending or disabled. Review its text in **Skills** in the console, then enable it only if the instructions are appropriate. If an import fails, check that the folder has a readable `SKILL.md`, use `nano-agent skills --help` for the accepted input types, and keep the source URL private if it contains access credentials.
