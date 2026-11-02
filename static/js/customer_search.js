// "Book for customer" (staff only): type part of an email, pick a customer.
// The server only sends the matches (at most 10), never the whole user list.
// The chosen customer's id goes in the hidden "customer" field; empty = myself.

const box = document.querySelector('.customer-search');
const search = document.getElementById('customer-search');
const customerId = document.getElementById('customer');
const filterCustomer = document.getElementById('filter-customer');
const list = document.getElementById('customer-results');
const chosen = document.getElementById('customer-chosen');
const MIN_LENGTH = 3; // Same as CUSTOMER_SEARCH_MIN_LENGTH in views.py.
const DELAY_MS = 250; // Wait until the user stops typing before asking the server.
let timer;

function choose(id, label) {
  customerId.value = id;
  filterCustomer.value = id;
  search.value = label;
  chosen.textContent = id ? `${chosen.dataset.chosen} ${label}` : chosen.dataset.myself;
  list.hidden = true;
}

function show(results) {
  list.replaceChildren();
  if (!results.length) {
    const empty = document.createElement('li');
    empty.textContent = chosen.dataset.noResults;
    empty.className = 'muted';
    list.append(empty);
  }
  results.forEach(({ id, label }) => {
    const item = document.createElement('li');
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = label; // textContent, never innerHTML: names are user input.
    button.addEventListener('click', () => choose(String(id), label));
    item.append(button);
    list.append(item);
  });
  list.hidden = false;
}

search.addEventListener('input', () => {
  // Typing again means the previous choice no longer matches the text.
  customerId.value = '';
  filterCustomer.value = '';
  chosen.textContent = search.value.trim() ? chosen.dataset.notChosen : chosen.dataset.myself;

  clearTimeout(timer);
  const query = search.value.trim();
  if (query.length < MIN_LENGTH) {
    list.hidden = true;
    return;
  }
  timer = setTimeout(async () => {
    const response = await fetch(`${box.dataset.url}?q=${encodeURIComponent(query)}`);
    if (response.ok) show((await response.json()).results);
  }, DELAY_MS);
});

// Text typed but no customer picked: stop, instead of silently booking for myself.
document.getElementById('slot-picker').addEventListener('submit', (event) => {
  if (search.value.trim() && !customerId.value) {
    event.preventDefault();
    chosen.textContent = chosen.dataset.notChosen;
    search.focus();
  }
});
