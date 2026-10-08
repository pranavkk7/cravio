// Ask Cravio: the chat panel. The server does all the AI work (assistant/agent.py); this only sends the
// customer's message, shows the reply, and keeps the cart badge in the nav up to date.
// On the public demo the server has no API key, so visitors can use their own: it is kept in
// sessionStorage (this tab only) and sent in a header with each message, never stored server-side.
const root = document.querySelector('[data-assistant]')

if (root) {
  const panel = root.querySelector('.ask-panel')
  const fab = root.querySelector('.ask-fab')
  const log = root.querySelector('[data-ask-log]')
  const form = root.querySelector('[data-ask-form]')
  const input = form.elements.message
  const suggestions = root.querySelector('[data-ask-suggestions]')
  const keyForm = root.querySelector('[data-ask-key]')
  const forget = root.querySelector('[data-ask-forget]')
  const OPEN_KEY = 'cravio.assistant.open'
  const API_KEY = 'cravio.assistant.apiKey'
  let loaded = false
  let busy = false
  let serverHasKey = true

  const storedKey = () => { try { return sessionStorage.getItem(API_KEY) || '' } catch { return '' } }
  const storeKey = (key) => {
    try { key ? sessionStorage.setItem(API_KEY, key) : sessionStorage.removeItem(API_KEY) } catch {}
    forget.hidden = !key
  }

  // Swap the message box for the key form, or back.
  const askForKey = (show) => {
    keyForm.hidden = !show
    form.hidden = show
    if (show) {
      suggestions.hidden = true
      keyForm.elements.key.focus()
    }
  }

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
      serverHasKey = data.enabled
      data.messages.forEach((m) => add(m.role, m.text))
      if (data.messages.length) suggestions.hidden = true
      forget.hidden = !storedKey()
      if (!serverHasKey && !storedKey()) askForKey(true)
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
      const headers = { Accept: 'application/json' }
      if (storedKey()) headers['X-Anthropic-Key'] = storedKey()
      const response = await fetch(root.dataset.chatUrl, { method: 'POST', body, headers })
      const data = await response.json()
      typing.remove()
      if (!response.ok) {
        add('error', data.error || 'Something went wrong. Please try again.')
        if (data.need_key) {
          storeKey('')
          askForKey(true)
        }
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

  keyForm.addEventListener('submit', (event) => {
    event.preventDefault()
    const key = keyForm.elements.key.value.trim()
    if (!key.startsWith('sk-ant-')) {
      add('error', "That doesn't look like a Claude API key. It starts with sk-ant-.")
      return
    }
    keyForm.reset()
    storeKey(key)
    askForKey(false)
    suggestions.hidden = log.querySelectorAll('.ask-msg.user').length > 0
    add('assistant', 'Key saved for this tab. What are you craving?')
    input.focus()
  })
  forget.addEventListener('click', () => {
    storeKey('')
    add('assistant', 'Your API key is removed from this tab.')
    if (!serverHasKey) askForKey(true)
  })

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
