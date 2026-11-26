# Safety net: change the engine without breaking old stories

If new stories keep extending the engine, the old ones must keep rendering the same.

1. **Golden frames.** `scripts/golden_hashes.py record|check` hashes chosen frames of reference stories. Keep one small
   reference part per capability (orbit, don, climb, a duel...). Run `check` before and after an engine change; a
   changed hash must be an intended change (re-record) or a bug.
2. **Generated docs, one source.** The writer guides (`docs/story-writter/*`) and the manifest are generated or checked
   from the schemas, so they cannot go stale. Today `stage.md` and `script.md` are edited by hand in parallel: fix that.
3. **Contract tests stay small.** A pure function per capability (as `heightAt`, `donDef`, `wearOn`) with a unit test, a
   planner test with a fake story, and the schema export. No browser needed (the laptop cannot run the full suites).
4. **Add-a-feature checklist** (when a gap really needs code):
   - add a row to `gap-log.md`; decide the fragment;
   - schema (`pipeline/scribble/schemas`) -> planner (`stages/shots.py`) -> engine (`engine/page`) -> validator;
   - export the schemas (`python -m pipeline.scribble.schemas.export`) and the manifest (`scripts/capabilities.py`);
   - update `docs/story-writter/stage.md`, `script.md` and the Help page;
   - one pure-function test and one planner test; run only those;
   - note the limit lifted in `capabilities.py` `LIMITS` and in the gap log.
5. **Never edit during a job.** Check the job table first (a dev reload kills a running render).
