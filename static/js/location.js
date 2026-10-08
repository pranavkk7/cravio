// "Use my location": asks the browser for the position, then posts it to the server.
// Without JavaScript the area picker next to it still works, so this is only an enhancement.
document.querySelectorAll('[data-locate]').forEach((form) => {
  const button = form.querySelector('[data-locate-button]')
  const status = form.closest('.deliver')?.querySelector('[data-locate-status]')
  const say = (text) => { if (status) status.textContent = text }

  form.addEventListener('submit', (event) => {
    event.preventDefault()
    if (!('geolocation' in navigator)) {
      say('Your browser cannot share its location. Please choose your area instead.')
      return
    }
    button.disabled = true
    say('Finding you...')
    navigator.geolocation.getCurrentPosition(
      (position) => {
        form.elements.lat.value = position.coords.latitude.toFixed(5)
        form.elements.lng.value = position.coords.longitude.toFixed(5)
        form.submit()
      },
      (error) => {
        button.disabled = false
        say(error.code === error.PERMISSION_DENIED
          ? 'Location permission was declined. Please choose your area instead.'
          : 'We could not find your location. Please choose your area instead.')
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 },
    )
  })
})
