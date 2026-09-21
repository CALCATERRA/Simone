# Simone — Cloudflare Worker

Cloudflare version of Simone.

The existing Appwrite code in the repository root (`src/`) is intentionally untouched.

This first migration build only tests Worker → D1 connectivity.

## Configuration

- Worker: `simone`
- D1 database: `simone-memory`
- D1 binding: `DB`

Secrets must never be committed to GitHub. Gemini, Instagram and OpenWeather
credentials will be configured later as Cloudflare Worker secrets.

## Next migration step

Port the existing Simone Instagram/Gemini/OpenWeather logic into this Worker,
then enable persistent per-user memory through D1.
