import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import '@fontsource/inter/400.css'
import '@fontsource/inter/500.css'
import '@fontsource/inter/600.css'
import '@fontsource/shantell-sans/500.css'
import '@fontsource/shantell-sans/600.css'
import App from './App.vue'
import './style.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: () => import('./pages/Overview.vue') },
    // Retain old bookmarks while the Story Writer UI is retired.
    { path: '/story-writer', redirect: '/new-series' },
    { path: '/story-writer/review', redirect: '/new-series' },
    { path: '/series', name: 'series', component: () => import('./pages/SeriesList.vue') },
    { path: '/new-series', name: 'new-series', component: () => import('./pages/NewSeries.vue') },
    { path: '/series/:slug/new-part', name: 'new-part', component: () => import('./pages/NewPart.vue'), props: true },
    { path: '/series/:slug', name: 'series-detail', component: () => import('./pages/SeriesDetail.vue'), props: true },
    { path: '/series/:slug/cast/:id', name: 'cast-edit', component: () => import('./pages/CastEditor.vue'), props: true },
    { path: '/series/:slug/:part', name: 'part', component: () => import('./pages/PartDetail.vue'), props: true },
    { path: '/review', name: 'review', component: () => import('./pages/Review.vue') },
    { path: '/gallery', name: 'gallery', component: () => import('./pages/Gallery.vue') },
    { path: '/notifications', name: 'notifications', component: () => import('./pages/Notifications.vue') },
    { path: '/creatures', name: 'creatures', component: () => import('./pages/Creatures.vue') },
    { path: '/creatures/:id', name: 'creature-edit', component: () => import('./pages/CreatureEditor.vue'), props: true },
    { path: '/props', name: 'props', component: () => import('./pages/Props.vue') },
    { path: '/expressions', name: 'expressions', component: () => import('./pages/Expressions.vue') },
    { path: '/props/:id', name: 'prop-edit', component: () => import('./pages/PropEditor.vue'), props: true },
    { path: '/wardrobe', name: 'wardrobe', component: () => import('./pages/Wardrobe.vue') },
    { path: '/wardrobe/:id', name: 'wardrobe-edit', component: () => import('./pages/WardrobeEditor.vue'), props: true },
    { path: '/sets', name: 'sets', component: () => import('./pages/Sets.vue') },
    { path: '/sets/:id', name: 'set-edit', component: () => import('./pages/SetEditor.vue'), props: true },
    { path: '/objects', name: 'objects', component: () => import('./pages/Objects.vue') },
    { path: '/sounds', name: 'sounds', component: () => import('./pages/Sounds.vue') },
    { path: '/actions', name: 'actions', component: () => import('./pages/Actions.vue') },
    { path: '/actions/:id', name: 'action-edit', component: () => import('./pages/ActionEditor.vue'), props: true },
    { path: '/help', name: 'help', component: () => import('./pages/Help.vue') },
    { path: '/posted', name: 'posted', component: () => import('./pages/Posted.vue') },
    { path: '/history', name: 'history', component: () => import('./pages/History.vue') },
    { path: '/settings', name: 'settings', component: () => import('./pages/Settings.vue') },
  ],
})

createApp(App).use(router).mount('#app')
