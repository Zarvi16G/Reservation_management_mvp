// Dummy payment: show "Processing..." for a moment, as a real gateway would,
// then send the form. The server books the slots when the form arrives.
// Without JavaScript the form is simply sent straight away. The texts come
// from data-* attributes in checkout.html, so they are translated there.

const form = document.getElementById('payment-form');
const status = document.getElementById('payment-status');
const PROCESSING_MS = 2000;
const APPROVED_MS = 800;

form.addEventListener('submit', (event) => {
  event.preventDefault();
  form.querySelector('button').disabled = true; // No double payments.

  status.textContent = status.dataset.processing;
  status.classList.add('processing');

  setTimeout(() => {
    status.textContent = `✓ ${status.dataset.approved}`;
    status.classList.replace('processing', 'approved');
    // form.submit() does not fire "submit" again, so this runs only once.
    setTimeout(() => form.submit(), APPROVED_MS);
  }, PROCESSING_MS);
});
