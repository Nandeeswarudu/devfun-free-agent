# DevFun free agent

Nandu AI is registered and active in DevFun Arena.

- **Handle:** `Nandu`
- **Agent ID:** `cmvnnuyg8b7w6m200udq70qbj`
- **Competition:** `[TCG] Playground S4`
- **Competition ID:** `cmvmddsux8tt6ymnx3teo78ie`
- **Entry mode:** owner-hosted practice
- **Cost / stakes:** free practice; no money is staked
- **Season allowance:** up to 1,500 matches shared across versions, based on the latest season announcement

## Run free practice matches in batches

Open **Actions → Enter free TCG Playground Season 4 → Run workflow** in GitHub. Choose **1, 3, or 5** matches for that run; the default is **5**. During provider testing, run just **1** match first.

The workflow verifies that the exact season is still active and open before playing. It stores the outcome and match count in `.arena-tcg-state` after every settled match, and stops starting matches at the 1,500-match season limit. Runs are serialized so two batches from this workflow do not overlap. There is no schedule enabled; a batch starts only when you manually run the workflow or push the dedicated trigger file.

[Open the GitHub Actions page](https://github.com/Nandeeswarudu/devfun-free-agent/actions).

The Arena accepted the owner-hosted join, so this season is being played through `/tcg/join`; it does not create a hosted-bundle submission record. The same saved deck is used when re-entering. See `.arena-tcg-state` for the deck list and practice log.

## Strategy

`harness/strategy.py` uses live card and attack metadata copied into the runner's temporary bundle. Mistral integration uses the official chat-completions endpoint and the `mistral-small-latest` model. The workflow reads `MISTRAL_API_KEY` from GitHub Actions Secrets; the key is never stored in the repository.

To conserve Free-mode usage, the agent makes at most **one Mistral request per match**, only for choices with a compact set of legal actions. If the key, model, API, network, or free-tier quota is unavailable, it falls back to the local rule-based strategy. Mistral's docs say Studio Free mode includes limited usage and rate limits; confirm your organization remains on Free mode and pay-as-you-go is not enabled if you need to avoid charges. [Mistral API key setup](https://docs.mistral.ai/getting-started/quickstarts/studio/activate-and-generate-api-key) · [API usage limits](https://docs.mistral.ai/admin/billing-usage/usage-limits)

Before starting a match, use **Actions → Test Mistral API (no Arena match) → Run workflow**. It makes one small API request and does not enter a game.

## Practice log

Saved match count currently starts at **9** recorded/estimated matches. Earlier practice losses included:
- Match `2950b773-c8c9-412d-9336-63ffbeb917a4`: opponent **Ironclad**; loss reason `no_active_pokemon`.
- Match `974753e2-73f7-4dc6-8a3d-5b18e3a0e611`: loss reason `all_prizes_taken`.

The saved state tracks settled matches and one prior terminal match whose exact outcome was not captured. These runs are practice-only and no money is staked.
