<script setup lang="ts">
import { Smile } from 'lucide-vue-next'
import LibraryCard from '../components/LibraryCard.vue'
import LibrarySection from '../components/LibrarySection.vue'
import WardrobePreview from '../components/WardrobePreview.vue'
import { expressionNote, expressionOptions } from '../lib/expressions'

// Expressions are hand-drawn by the engine and shared by every series.
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-baseline gap-3">
      <h2 class="font-display text-2xl font-semibold">Expressions</h2>
      <span class="text-sm text-muted">{{ expressionOptions.length }} built-in face expressions</span>
    </div>
    <p class="text-sm text-muted">
      Shared expressions for cast defaults, story actions and wardrobe layer conditions. Use one as
      <code>"default_expression": "worried"</code> in cast JSON or as <code>"when": ["worried"]</code> on a wardrobe layer.
    </p>
    <LibrarySection id="builtin" title="Built in" :count="expressionOptions.length">
      <LibraryCard v-for="expression in expressionOptions" :key="expression.id" :name="expression.name"
        :code="expression.id" tag="built in" :note="expressionNote[expression.id]" :icon="Smile"
        readonly="engine face drawing: read only">
        <template #preview>
          <WardrobePreview :expression="expression.id" :label="`Stickman with ${expression.name} expression`" class="h-full w-full" />
        </template>
      </LibraryCard>
    </LibrarySection>
  </div>
</template>
