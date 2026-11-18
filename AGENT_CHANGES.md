# Agent handoff

## OmniRoute model monitor

- Added an OmniRoute model-discovery endpoint using the configured gateway key.
- Added automatic model refresh in Settings, with responsive three-column cards, context-window metadata, pricing badges, pricing filters, and model selection.
- Regenerated the OpenAPI document and frontend API types.
- Kept pricing conservative: models are marked Free only when OmniRoute explicitly reports them as free; otherwise they show Paid / varies.

Validation completed: Python compilation and frontend typecheck/build passed. Focused pytest execution was blocked by the environment denying access to its temporary pytest directory.

- Added sideways custom actions with automatic left/right facing.
- Added custom movement speed; negative values support backward glides/moonwalks.
- Updated planning, validation, API schemas, action editor, and AI action import prompts.
- Added regression coverage for sideways and moving actions.

Validation completed: Python action/schema tests, API checks, web tests/build, and engine tests passed.

## AI providers and Story Writer

- Added selectable AI providers: OmniRoute, Google Gemini, and OpenRouter.
- Added native Gemini `generateContent` requests and OpenRouter's OpenAI-compatible chat endpoint.
- Kept provider keys server-side and added separate key/model settings for each provider.
- Settings now has separate Preferences, OmniRoute, Gemini, and OpenRouter sections.
- Saved API keys show only their final four characters; full keys are never returned to the UI.
- Added Gemini model discovery using the saved or typed key, filtering to usable text-generation models and recommending a stable Flash model.
- Added OpenRouter configuration with `openrouter/free` as the starter model option.
- Restricted Story Writer to dedicated providers, excluding OmniRoute.
- Added the Story Writer module: sends the Story Guide and current library inventory to Gemini/OpenRouter, previews a multi-part plan, creates returned custom props/sets/creatures/actions, then creates the series and parts.
- Kept FreeTTS generation and audio upload manual as requested.

## Navigation and UI

- Reorganized the sidebar into Studio and Library navigation groups.
- Moved Posted, History, Help, and Settings into a floating bottom-right utility gear menu.
- Added a quarter-arc reveal animation for utility links.
- Active utility pages use the accent color, and the gear remains spinning while one is open.
- Fixed the floating gear's circular shape and centered icon alignment.

Validation completed: backend compilation, OpenAPI regeneration/export checks, focused API settings/completion tests, and frontend TypeScript checks passed.
