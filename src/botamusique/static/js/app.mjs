// New application code
import './main.mjs';

import Theme from './lib/theme.mjs';

document.addEventListener('DOMContentLoaded', () => {
  Theme.init();

  document.getElementById('theme-switch-btn').addEventListener('click', () => {
    Theme.swap();
  });
});
