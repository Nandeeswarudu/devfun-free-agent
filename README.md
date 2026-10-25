# DevFun free agent

Nandu AI is registered and active in DevFun Arena.

- **Handle:** `Nandu`
- **Agent ID:** `cmvnnuyg8b7w6m200udq70qbj`
- **Competition:** `[TCG] Playground S4`
- **Competition ID:** `cmvmddsux8tt6ymnx3teo78ie`
- **Entry mode:** owner-hosted practice
- **Cost / stakes:** free; no prizes or money at stake
- **Season allowance:** up to 300 matches shared across versions

## Run a free practice match

No local clone is required. In GitHub, open **Actions → Enter free TCG Playground Season 4 → Run workflow**. The workflow checks that the exact season is still active and open, reuses the same deck, joins the practice queue, and runs `harness/strategy.py` for the match.

The Arena accepted the owner-hosted join, so this season is being played through `/tcg/join`; it does not create a hosted-bundle submission record. The same deck is sent again when re-entering. Use the saved deck list in `.arena-tcg-state` as the source of truth. Avoid running multiple jobs manually at once; the workflow has a concurrency guard.

## Strategy

`harness/strategy.py` uses live card and attack metadata copied into the runner's temporary bundle. It prefers legal card plays / bench setup, energy attachments, and attacks. The game sandbox has no network access, and the strategy does not call a paid model API.

## Practice log

Two free practice matches have settled so far. Both were losses:
- Match `2950b773-c8c9-412d-9336-63ffbeb917a4`: opponent **Ironclad**; loss reason `no_active_pokemon`.
- Match `974753e2-73f7-4dc6-8a3d-5b18e3a0e611`: loss reason `all_prizes_taken`.

These results are for practice only, with no money at stake. See `.arena-tcg-state` for the deck list and match IDs. The agent has not entered a paid or ranked competition.
