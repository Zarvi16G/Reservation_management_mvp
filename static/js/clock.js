// The header clock: the time where the courts are (data-tz), like a scoreboard.
// Without JavaScript it shows the time the page was loaded.
document.querySelectorAll('[data-clock]').forEach((clock) => {
  const zone = clock.dataset.tz;
  const city = clock.querySelector('[data-clock-city]');
  const time = clock.querySelector('[data-clock-time]');
  const format = new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
    timeZone: zone,
  });

  city.textContent = zone.split('/').pop().replaceAll('_', ' '); // America/Bogota → Bogota
  const tick = () => {
    time.textContent = format.format(new Date());
  };
  tick();
  setInterval(tick, 15000);
});
