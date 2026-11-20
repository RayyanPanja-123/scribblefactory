<script setup lang="ts">
// Story writing tips, shown beside the story editor (Text and Painter views)
const TIPS: [string, string][] = [
  ['What lasts', 'Place, On stage and Weather stay until you change them. Action, Face, Effect and Sound only touch their own line.'],
  ['Sound mid-sentence', 'Split the line where the sound goes (+ line below) and add the Sound to the second half. It plays as that half starts.'],
  ['Sound after a line', 'Add the Sound to the next line instead.'],
  ['Pause for a sound', 'End the first half with "..." so the voice takes a breath; the sound plays over the voice otherwise.'],
  ['Someone walks in', 'Add On stage with them right above the line they appear on.'],
  ['Two people act at once', 'Switch to Text and write one line: @do ava: wave, ben: cheer.'],
  ['The twist', 'Exactly one, on the last line. It gets a push-in, the music stops and a low hit lands.'],
  ['Go easy', 'At most 5 sounds (never on back-to-back lines) and 3 lightning bolts. Pop is for reveals, shake for hits.'],
  ['Numbers', 'Write them as words: "eighteen million", not "18 million".'],
  ['Changed the words?', 'Every line is spoken. If the voice is already recorded, record it again.'],
  ['Not sure?', 'Save, then Check: it names the line of every mistake.'],
]
</script>

<template>
  <aside class="raised p-6 lg:sticky lg:top-4" aria-labelledby="story-tips">
    <h4 id="story-tips" class="font-display text-lg font-semibold">Tips and tricks</h4>
    <dl class="mt-3 space-y-3 text-sm">
      <div v-for="[t, d] in TIPS" :key="t">
        <dt class="font-semibold text-ink">{{ t }}</dt>
        <dd class="text-muted">{{ d }}</dd>
      </div>
    </dl>
  </aside>
</template>
