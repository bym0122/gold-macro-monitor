# Security

- Never commit API keys, tokens, or personal holdings.
- `FRED_API_KEY` must live only in GitHub Actions Secrets.
- Workflow permissions are minimized; `contents: write` is required only to push daily data/reports into this private repo.
- If Notion integration is added later, use a dedicated integration token with least privilege and inject via `NOTION_TOKEN` secret.
- Do not log secret values in Actions output or report files.
