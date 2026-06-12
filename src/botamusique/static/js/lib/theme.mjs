export default class {
    /**
     * @property {boolean} dark Interal state for dark theme activation.
     * @private
     */
    static #dark = false;

    /**
     * Inialize the theme class.
     */
    static init() {
      // Check LocalStorage for dark theme selection
      if (localStorage.getItem('darkTheme') === 'true') {
        // Update page theme
        this.set(true);
      }
    }

    /**
     * Set page theme and update local storage variable.
     *
     * @param {boolean} dark Whether to activate dark theme.
     */
    static set(dark = false) {
      // Swap CSS to selected theme
      document.getElementById('pagestyle')
          .setAttribute('href', 'static/css/' + (dark ? 'dark' : 'main') + '.css');

      // Expose the active theme to CSS. The light (flatly) theme carries a
      // `data-bs-theme=light` hook so shared custom rules can target it; the
      // dark (darkly) theme keeps no attribute so it renders via its :root
      // defaults unchanged.
      if (dark) {
        document.documentElement.removeAttribute('data-bs-theme');
      } else {
        document.documentElement.setAttribute('data-bs-theme', 'light');
      }

      // Update local storage
      localStorage.setItem('darkTheme', dark);

      // Update internal state
      this.#dark = dark;
    }

    /**
     * Swap page theme.
     */
    static swap() {
      this.set(!this.#dark);
    }
}
