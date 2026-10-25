# DevFun free agent

Nandu AI is registered and active in DevFun Arena.

- **Handle:** `Nandu`
- **Agent ID:** `cmvnnuyg8b7w6m200udq70qbj`
- **Competition:** `[TCG] Playground S4`
- **Competition ID:** `cmvmddsux8tt6ymnx3teo78ie`
- **Entry mode:** owner-hosted practice
- **Cost / stakes:** free; no prizes or money at stake
- **Season allowance:** up to 300 matches shared across versions

## Run free practice matches in batches

Open **Actions → Enter free TCG Playground Season 4 → Run workflow** in GitHub. Choose **1, 3, or 5** matches for that run; the default is **5**. Nandu AI plays its own turns automatically for each match, then starts the next match in the batch.

The workflow verifies that the exact season is still active and open before playing. It stores the outcome and match count in `.arena-tcg-state` after every settled match, and stops starting matches at the 300-match season limit. Runs are serialized so two batches from this workflow do not overlap. There is no schedule enabled; a batch starts only when you manually run the workflow or push the dedicated trigger file.

[Open the GitHub Actions page](https://github.com/Nandeeswarudu/devfun-free-agent/actions).

The Arena accepted the owner-hosted join, so this season is being played through `/tcg/join`; it does not create a hosted-bundle submission record. The same saved deck is used when re-entering. See `.arena-tcg-state` for the deck list and practice log.

## Strategy

`harness/strategy.py` uses live card and attack metadata copied into the runner's temporary bundle. Groq integration is implemented for `openai/gpt-oss-20b`, but calls are **temporarily disabled** because Groq's Cloudflare edge returned non-retryable Error 1010 (`browser_signature_banned`) to both the model-list and chat-completions tests. The bot therefore uses its local rule-based strategy until Groq support resolves the block. The workflow passes `GROQ_API_KEY` from GitHub Actions Secrets; no key is stored in the repository.

Cloudflare's guidance for Error 1010 is to notify the website owner; only Groq can review this block for `api.groq.com`. See [Cloudflare Error 1010](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1010/).

## Practice log

Two free practice matches had settled before batch mode was added. Both were losses:
- Match `2950b773-c8c9-412d-9336-63ffbeb917a4`: opponent **Ironclad**; loss reason `no_active_pokemon`.
- Match `974753e2-73f7-4dc6-8a3d-5b18e3a0e611`: loss reason `all_prizes_taken`.

These results are for practice only, with no money at stake. The agent has not entered a paid or ranked competition.
