# Key rotation (required)

API keys for Nebius Token Factory and Tavily were present in a local `.env`
during development and must be treated as **exposed**.

## Do this before any public push

1. **Nebius:** console.nebius.com → API keys → revoke the old key → create a new one → update `.env` `NEBIUS_API_KEY` (and Contree token if shared).
2. **Tavily:** app.tavily.com → rotate/revoke `TAVILY_API_KEY` → update `.env`.
3. Confirm `.env` is gitignored (`git check-ignore -v .env`).
4. Never commit `.env`. Only `.env.example` (empty values) belongs in git.

This file intentionally contains **no secrets**.
