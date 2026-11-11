'use strict';
const toast = document.querySelector('#toast');
let timer;
async function copyText(button, text) {
  try {
    await navigator.clipboard.writeText(text);
    toast.textContent = 'Copied to clipboard';
  } catch {
    toast.textContent = 'Select the text and copy it manually.';
  }
  toast.classList.add('visible');
  clearTimeout(timer);
  timer = setTimeout(() => toast.classList.remove('visible'), 2500);
}
document.querySelectorAll('.copy').forEach(button => button.addEventListener('click', () => copyText(button, button.parentElement.querySelector('p').textContent.trim())));
document.querySelectorAll('.copy-url').forEach(button => button.addEventListener('click', () => copyText(button, button.parentElement.querySelector('a, code').textContent.trim())));
const search = document.querySelector('#endpoint-search');
const endpoints = Array.from(document.querySelectorAll('.endpoint'));
function filterEndpoints() {
  const query = search.value.toLowerCase().trim();
  let visible = 0;
  endpoints.forEach(endpoint => {
    endpoint.hidden = !endpoint.textContent.toLowerCase().includes(query);
    if (!endpoint.hidden) visible++;
  });
  document.querySelector('#endpoint-count').textContent = `${visible} of ${endpoints.length}`;
  document.querySelector('#no-results').hidden = visible !== 0;
}
search.addEventListener('input', filterEndpoints);
filterEndpoints();
