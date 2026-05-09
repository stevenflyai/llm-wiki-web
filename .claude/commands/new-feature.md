# /new-feature — 启动新功能的标准流程

You are starting a new feature for `llm-wiki-web`.

**Your job in this session is ONLY to produce a SPEC. Do NOT write any code.**

## Step 1: Read context

Read these files in order:
1. `docs/dev/CLAUDE-DEV.md` — development contract
2. `DECISIONS.md` — architecture decisions you must respect
3. `BACKLOG.md` — existing ideas
4. `docs/specs/_TEMPLATE.md` — the SPEC template you'll use

## Step 2: Identify the feature

Ask the user:
- "Which BACKLOG item are we promoting? Or is this a fresh idea?"
- If fresh, suggest adding it to BACKLOG first.

## Step 3: Interview the user

Use the `AskUserQuestion` tool to dig into:

- **Problem** — what pain triggered this?
- **Goals & Non-Goals** — what's in, what's out
- **Provider compatibility** — which LLM providers must this work with?
- **Wiki schema impact** — does this change frontmatter / INDEX / LOG / new dirs?
- **Failure modes** — what can go wrong?
- **Test strategy** — how do we verify?
- **Open questions** — alternatives, trade-offs

**Do not ask obvious questions. Dig into the hard parts.**
**Keep interviewing until there are zero Open Questions.**

## Step 4: Write the SPEC

- Copy `docs/specs/_TEMPLATE.md` to `docs/specs/draft/<feature-slug>.md`
- Fill in every section
- Slug should be 2-4 kebab-case words
- Set Status to "Draft"

## Step 5: End the session

Tell the user:
> SPEC drafted at `docs/specs/draft/<slug>.md`. Review it.
> If approved, run `git mv` to `approved/` then start a fresh session for planning.
> Do NOT have me implement in this same session — context should be clean.

**Do not generate PLAN.md. Do not write code. End here.**
