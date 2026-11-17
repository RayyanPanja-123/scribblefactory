declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent
  export default component
}

// Vite `?raw` imports: the file's text (Overview copies docs/STORY_GUIDE.md this way)
declare module '*?raw' {
  const text: string
  export default text
}
