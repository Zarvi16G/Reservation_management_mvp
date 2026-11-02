// Slot picker: "Select all" per court and day, and the result pop-up.
// Without JavaScript the page still works: slots can be ticked one by one.

document.querySelectorAll('[data-select-all]').forEach((toggle) => {
  const row = toggle.closest('.slot-row');
  const slots = row.querySelectorAll('input[name="slot"]');

  toggle.addEventListener('change', () => {
    slots.forEach((slot) => { slot.checked = toggle.checked; });
  });

  // Keep "Select all" in sync when slots are ticked by hand.
  slots.forEach((slot) => {
    slot.addEventListener('change', () => {
      toggle.checked = [...slots].every((s) => s.checked);
    });
  });
});

// The dialog is rendered "open" so it shows even without JavaScript; with
// JavaScript, reopen it as a modal (dark backdrop, focus inside it).
const result = document.getElementById('booking-result');
if (result) {
  result.close();
  result.showModal();
}
