import DefaultTheme from "vitepress/theme"
import type { Theme } from "vitepress"
import Layout from "./Layout.vue"
import Diagram from "./Diagram.vue"
import "./custom.css"
import "./polish.css"

export default {
  extends: DefaultTheme,
  Layout,
  enhanceApp({ app }) {
    app.component("Diagram", Diagram)
    // Pause every animation while the tab is hidden.
    if (typeof document !== "undefined") {
      const sync = () => document.documentElement.classList.toggle("v-hidden", document.hidden)
      document.addEventListener("visibilitychange", sync)
      sync()
    }
  },
} satisfies Theme
