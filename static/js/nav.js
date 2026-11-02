// Phones: open and close the menu with the ☰ button.
// From the md breakpoint up, Tailwind's md: classes always show the menu.

const toggle = document.querySelector('[data-nav-toggle]');
const nav = document.querySelector('[data-nav]');
const DESKTOP = window.matchMedia('(min-width: 48rem)'); // Tailwind's md breakpoint.

function setOpen(open) {
  toggle.setAttribute('aria-expanded', String(open));
  nav.hidden = !open && !DESKTOP.matches;
}

setOpen(false); // Without JavaScript it stays open, so the links are always reachable.
toggle.addEventListener('click', () => setOpen(nav.hidden));
DESKTOP.addEventListener('change', () => setOpen(false));
