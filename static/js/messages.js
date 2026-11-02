// Add a ✕ button to each message (success, error...) so it can be closed.
// Without JavaScript the messages are simply shown until the next page.

document.querySelectorAll('[data-message]').forEach((message) => {
  const close = document.createElement('button');
  close.type = 'button';
  close.textContent = '✕';
  close.className = 'shrink-0 border-0 p-0';
  close.setAttribute('aria-label', message.parentElement.dataset.closeLabel); // Translated in base.html.
  close.addEventListener('click', () => message.remove());
  message.append(close);
});
