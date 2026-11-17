import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import '@fontsource/inter/400.css'
import '@fontsource/inter/500.css'
import '@fontsource/inter/600.css'
import '@fontsource/fredoka/500.css'
import '@fontsource/fredoka/600.css'
import App from './App.vue'
import './style.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: () => import('./pages/Overview.vue') },
    { path: '/series', name: 'series', component: () => import('./pages/SeriesList.vue') },
    { path: '/new-series', name: 'new-series', component: () => import('./pages/NewSeries.vue') },
    { path: '/series/:slug/new-part', name: 'new-part', component: () => import('./pages/NewPart.vue'), props: true },
    { path: '/series/:slug', name: 'series-detail', component: () => import('./pages/SeriesDetail.vue'), props: true },
    { path: '/series/:slug/:part', name: 'part', component: () => import('./pages/PartDetail.vue'), props: true },
    { path: '/review', name: 'review', component: () => import('./pages/Review.vue') },
    { path: '/posted', name: 'posted', component: () => import('./pages/Posted.vue') },
  ],
})

createApp(App).use(router).mount('#app')
