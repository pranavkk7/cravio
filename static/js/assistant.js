// Ask Cravio: the chat panel. The server does all the AI work (assistant/agent.py); this only sends the
// customer's message, shows the reply, and keeps the cart badge in the nav up to date.
const root = document.querySelector('[data-assistant]')

if (root) {
  const panel = root.querySelector('.ask-panel')
  const fab = root.querySelector('.ask-fab')
  const log = root.querySelector('[data-ask-log]')
  const form = root.querySelector('[data-ask-form]')
  const input = form.elements.message
  const suggestions = root.querySelector('[data-ask-suggestions]')
  const OPEN_KEY = 'cravio.assistant.open'
  let loaded = false
  let busy = false

  const remember = (open) => { try { sessionStorage.setItem(OPEN_KEY, open ? '1' : '') } catch {} }

  // Text from the server is escaped first, then **bold** and line breaks are allowed back in.
  const format = (text) => {
    const escaped = text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)
    return escaped.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/\n/g, '<br>')
  }

  const add = (role, text, extra = '') => {
    const bubble = document.createElement('div')
    bubble.className = `ask-msg ${role}`
    bubble.innerHTML = format(text) + extra
    log.append(bubble)
    log.scrollTop = log.scrollHeight
    return bubble
  }

  const setCartCount = (count) => {
    const pill = document.querySelector('.cart-pill')
    if (!pill) return
    let badge = pill.querySelector('.cart-count')
    if (!badge && count) {
      badge = document.createElement('span')
      badge.className = 'cart-count'
      pill.append(badge)
    }
    if (badge) badge.textContent = count
    if (badge && !count) badge.remove()
    pill.setAttribute('aria-label', `Cart, ${count} item${count === 1 ? '' : 's'}`)
  }

  const loadHistory = async () => {
    loaded = true
    try {
      const data = await (await fetch(root.dataset.historyUrl, { headers: { Accept: 'application/json' } })).json()
      if (!data.enabled) {
        add('error', 'The AI assistant is not set up on this server yet (it needs an Anthropic API key).')
        form.hidden = true
        suggestions.hidden = true
        return
      }
      data.messages.forEach((m) => add(m.role, m.text))
      if (data.messages.length) suggestions.hidden = true
    } catch {
      add('error', 'Could not load the chat. Please refresh the page.')
    }
  }

  const toggle = (open) => {
    panel.hidden = !open
    fab.setAttribute('aria-expanded', String(open))
    root.classList.toggle('is-open', open)
    remember(open)
    if (open) {
      if (!loaded) loadHistory()
      input.focus()
    }
  }

  const send = async (text) => {
    if (busy || !text.trim()) return
    busy = true
    suggestions.hidden = true
    add('user', text)
    input.value = ''
    const typing = add('assistant typing', '', '<span></span><span></span><span></span>')
    typing.setAttribute('aria-label', 'Ask Cravio is typing')
    try {
      const body = new FormData(form)
      body.set('message', text)
      const response = await fetch(root.dataset.chatUrl, { method: 'POST', body, headers: { Accept: 'application/json' } })
      const data = await response.json()
      typing.remove()
      if (!response.ok) {
        add('error', data.error || 'Something went wrong. Please try again.')
      } else {
        const link = data.cart_changed ? `<a class="ask-cart-link" href="${root.dataset.cartUrl}">View cart and pay →</a>` : ''
        add('assistant', data.reply, link)
        setCartCount(data.cart_count)
      }
    } catch {
      typing.remove()
      add('error', 'Could not reach the assistant. Check your connection and try again.')
    } finally {
      busy = false
      input.focus()
    }
  }

  root.querySelectorAll('[data-ask-toggle]').forEach((button) => button.addEventListener('click', () => toggle(panel.hidden)))
  form.addEventListener('submit', (event) => {
    event.preventDefault()
    send(input.value)
  })
  suggestions.addEventListener('click', (event) => {
    if (event.target.matches('button')) send(event.target.textContent)
  })
  root.querySelector('[data-ask-reset]').addEventListener('click', async () => {
    const body = new FormData(form)
    await fetch(root.dataset.resetUrl, { method: 'POST', body }).catch(() => {})
    log.querySelectorAll('.ask-msg:not(.ask-welcome)').forEach((m) => m.remove())
    suggestions.hidden = false
    input.focus()
  })
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !panel.hidden) toggle(false)
  })

  // Stay open while the customer moves between pages.
  try { if (sessionStorage.getItem(OPEN_KEY)) toggle(true) } catch {}
}
