/** a name as a library id: "Café Chair!" -> "cafe-chair" (lowercase words joined by single dashes) */
export const slugify = (s: string) => s.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
